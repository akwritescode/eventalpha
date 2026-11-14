"""RSS/Atom source. Fetching uses httpx (timeouts, conditional GET); parsing uses feedparser."""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from eventalpha.models import Article
from eventalpha.text import extract_exchange_tickers, html_to_text

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    category: str = "company"  # "company" (press releases) or "macro" (Fed, SEC)


@dataclass
class FeedResult:
    status: int
    etag: str | None = None
    last_modified: str | None = None
    entries: list[Any] = field(default_factory=list)


def fetch_feed(
    client: httpx.Client, url: str, etag: str | None = None, last_modified: str | None = None
) -> FeedResult:
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    resp = client.get(url, headers=headers)
    if resp.status_code == 304:
        return FeedResult(status=304, etag=etag, last_modified=last_modified)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Unparseable feed {url}: {parsed.bozo_exception}")
    return FeedResult(
        status=resp.status_code,
        etag=resp.headers.get("ETag"),
        last_modified=resp.headers.get("Last-Modified"),
        entries=list(parsed.entries),
    )


def _published(entry: Any) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return datetime.fromtimestamp(calendar.timegm(st), tz=UTC)
    return datetime.now(UTC)


def entry_to_article(feed: Feed, entry: Any) -> Article | None:
    link = entry.get("link")
    title = (entry.get("title") or "").strip()
    if not link or not title:
        return None
    summary_html = entry.get("summary") or ""
    summary = html_to_text(summary_html) if summary_html else None
    content = entry.get("content") or []
    body = html_to_text(content[0].get("value", "")) if content else None
    return Article(
        source=f"rss:{feed.name}",
        source_id=entry.get("id") or link,
        url=link,
        title=title,
        summary=summary,
        body=body,
        tickers=extract_exchange_tickers(f"{title}\n{summary or ''}\n{body or ''}"),
        published_at=_published(entry),
    )
