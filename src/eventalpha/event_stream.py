"""High-impact events → Redis Stream `eventalpha:events`.

After classification, articles rated material and company-specific are appended
to a Redis Stream. Consumers read it independently:

* the API's SSE endpoint (`/api/v1/stream/events`): clients resume from `Last-Event-ID`
* the API's Telegram relay: a consumer group, so it acks what it sent and resumes after restarts

Why a Stream rather than Postgres LISTEN/NOTIFY: a stream keeps history, so a consumer that
was offline catches up instead of silently missing events.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import redis

STREAM = "eventalpha:events"
STREAM_MAXLEN = 10_000  # approximate cap; older entries are trimmed
DEDUPE_TTL_SECONDS = 30 * 24 * 3600

MIN_MATERIALITY = 2.5  # on the 0 (routine) .. 3 (major) scale
MIN_COMPANY_SPECIFIC = 0.8
EVENT_FLAG_PROB = 0.7  # event types listed on the alert

# "Publish once per article" must be atomic: a retried task can't send a duplicate, and a
# crash between the dedupe mark and the XADD can't lose the event. Lua runs as one step.
_PUBLISH_ONCE = """
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) then
  return redis.call('XADD', KEYS[2], 'MAXLEN', '~', ARGV[2], '*', unpack(ARGV, 3))
end
return false
"""


def is_alert(score: Mapping[str, Any]) -> bool:
    return score["materiality"] >= MIN_MATERIALITY and score["company_specific"] >= MIN_COMPANY_SPECIFIC


def to_fields(article: Mapping[str, Any], score: Mapping[str, Any]) -> dict[str, str]:
    events = sorted((k for k, p in score["events"].items() if p >= EVENT_FLAG_PROB),
                    key=lambda k: -score["events"][k])
    return {
        "article_id": str(article["id"]),
        "title": article["title"],
        "tickers": ",".join(article.get("tickers") or []),
        "form_type": article.get("form_type") or "",
        "source": article["source"],
        "url": article["url"],
        "published_at": article["published_at"].isoformat(),
        "sentiment": score["sentiment"],
        "sentiment_score": f"{score['sentiment_score']:.3f}",
        "materiality": f"{score['materiality']:.2f}",
        "events": ",".join(events),
        "model": score["model"],
    }


def publish_alerts(
    client: redis.Redis, articles: Sequence[Mapping[str, Any]], scores: Sequence[Mapping[str, Any]]
) -> int:
    """Append qualifying articles to the stream; returns how many were newly published."""
    by_id = {a["id"]: a for a in articles}
    publish = client.register_script(_PUBLISH_ONCE)
    published = 0
    for score in scores:
        article = by_id.get(score["article_id"])
        if article is None or not is_alert(score):
            continue
        flat = [v for kv in to_fields(article, score).items() for v in kv]
        if publish(keys=[f"eventalpha:alerted:{article['id']}", STREAM],
                   args=[DEDUPE_TTL_SECONDS, STREAM_MAXLEN, *flat]):
            published += 1
    return published
