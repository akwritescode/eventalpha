"""Redis Streams between the pipeline and the API.

* `eventalpha:events`: high-impact events only (material and company-specific). The API relays
  these to the Telegram channel through a consumer group.
* `eventalpha:feed`: every new item in the Market Intelligence Stream (each classified filing or
  news item, each signal, each macro release). The web UI listens over Server-Sent Events to
  refresh the stream and raise browser notifications; nothing else has to poll.

Each item is published once (Lua: SET NX dedupe mark + XADD in one step), and only after the
database commit, so a stream never runs ahead of the warehouse. Consumers resume from the last ID
they saw, so an offline consumer catches up instead of missing items (unlike LISTEN/NOTIFY).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import redis

STREAM = "eventalpha:events"
STREAM_MAXLEN = 10_000  # approximate cap; older entries are trimmed
FEED_STREAM = "eventalpha:feed"
FEED_MAXLEN = 20_000
DEDUPE_TTL_SECONDS = 30 * 24 * 3600

MIN_MATERIALITY = 2.5  # on the 0 (routine) .. 3 (major) scale
MIN_COMPANY_SPECIFIC = 0.8
EVENT_FLAG_PROB = 0.7  # event types listed on the alert

_PUBLISH_ONCE = """
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) then
  return redis.call('XADD', KEYS[2], 'MAXLEN', '~', ARGV[2], '*', unpack(ARGV, 3))
end
return false
"""


def _publish_once(client: redis.Redis, dedupe_key: str, stream: str, maxlen: int, fields: Mapping[str, str]) -> bool:
    script = client.register_script(_PUBLISH_ONCE)
    flat = [v for kv in fields.items() for v in kv]
    return bool(script(keys=[dedupe_key, stream], args=[DEDUPE_TTL_SECONDS, maxlen, *flat]))


def is_alert(score: Mapping[str, Any]) -> bool:
    return score["materiality"] >= MIN_MATERIALITY and score["company_specific"] >= MIN_COMPANY_SPECIFIC


def _top_events(score: Mapping[str, Any]) -> list[str]:
    return sorted((k for k, p in score["events"].items() if p >= EVENT_FLAG_PROB), key=lambda k: -score["events"][k])


def to_fields(article: Mapping[str, Any], score: Mapping[str, Any]) -> dict[str, str]:
    """High-impact event fields (Telegram relay + SSE). No model identifiers: those stay internal."""
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
        "events": ",".join(_top_events(score)),
    }


def publish_alerts(
    client: redis.Redis, articles: Sequence[Mapping[str, Any]], scores: Sequence[Mapping[str, Any]]
) -> int:
    """Append qualifying articles to the high-impact stream; returns how many were newly published."""
    by_id = {a["id"]: a for a in articles}
    published = 0
    for score in scores:
        article = by_id.get(score["article_id"])
        if article is None or not is_alert(score):
            continue
        fields = to_fields(article, score)
        if _publish_once(client, f"eventalpha:alerted:{article['id']}", STREAM, STREAM_MAXLEN, fields):
            published += 1
    return published


def feed_fields(
    kind: str,
    ref: str,
    title: str,
    *,
    tickers: Sequence[str] = (),
    sentiment: str = "",
    impact: str = "normal",
    url: str = "",
    occurred_at: str = "",
    label: str = "",
) -> dict[str, str]:
    """A notification-sized description of one new stream item. `ref` matches the feed item id
    the API serves (e.g. "article:154", "signal:premarket:2026-11-13", "macro:bls:...")."""
    return {
        "kind": kind,
        "ref": ref,
        "title": title,
        "label": label,
        "tickers": ",".join(tickers),
        "sentiment": sentiment,
        "impact": impact,
        "url": url,
        "occurred_at": occurred_at,
    }


def publish_feed_items(client: redis.Redis, items: Sequence[Mapping[str, str]]) -> int:
    """Append new stream items to the feed stream, once each (keyed on `ref`)."""
    return sum(_publish_once(client, f"eventalpha:fed:{i['ref']}", FEED_STREAM, FEED_MAXLEN, i) for i in items)


def article_feed_items(
    articles: Sequence[Mapping[str, Any]], scores: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    by_id = {a["id"]: a for a in articles}
    out = []
    for s in scores:
        a = by_id.get(s["article_id"])
        if a is None:
            continue
        sec = a["source"] == "sec_edgar"
        out.append(
            feed_fields(
                "sec" if sec else "news",
                f"article:{a['id']}",
                a["title"],
                tickers=a.get("tickers") or [],
                sentiment=s["sentiment"],
                impact="high" if is_alert(s) else "normal",
                url=a["url"],
                occurred_at=a["published_at"].isoformat(),
                label=f"SEC · {a.get('form_type')}" if sec else "NEWS",
            )
        )
    return out
