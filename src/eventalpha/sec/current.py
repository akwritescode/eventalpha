"""SEC's "latest filings" Atom feed: filings within minutes of acceptance, before the
nightly daily index exists. Entries become the same IndexEntry the daily DAGs use, so a
filing seen here and again in the 01:00 index run upserts onto the same row.
"""

from __future__ import annotations

import re
from datetime import datetime

import feedparser

from eventalpha.sec.client import RateLimitedClient
from eventalpha.sec.index import IndexEntry

FEED_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}&company=&dateb="
            "&owner=include&start={start}&count=100&output=atom")
_TITLE = re.compile(r"^(?P<form>.+?) - (?P<company>.+) \((?P<cik>\d+)\) \((?P<role>[^)]+)\)$")
_ACCESSION = re.compile(r"accession-number=(\d{10}-\d{2}-\d{6})")


def parse_feed(xml: bytes | str) -> list[tuple[IndexEntry, datetime]]:
    out = []
    for e in feedparser.parse(xml).entries:
        title = _TITLE.match(e.get("title", ""))
        acc = _ACCESSION.search(e.get("id", ""))
        if not (title and acc):
            continue
        accepted = datetime.fromisoformat(e["updated"])
        cik = str(int(title["cik"]))
        entry = IndexEntry(form_type=title["form"].strip(), company=title["company"].strip(), cik=cik,
                           date_filed=accepted.date(), path=f"edgar/data/{cik}/{acc.group(1)}.txt")
        out.append((entry, accepted))
    return out


def fetch_current(client: RateLimitedClient, form: str, since: datetime, max_pages: int = 5) -> list[IndexEntry]:
    """Filings of `form` accepted after `since`, newest first, paging until older ones appear."""
    found: dict[str, IndexEntry] = {}
    for page in range(max_pages):
        resp = client.get(FEED_URL.format(form=form.replace(" ", "+"), start=page * 100))
        resp.raise_for_status()
        entries = parse_feed(resp.content)
        for entry, accepted in entries:
            if accepted > since:
                found.setdefault(entry.accession, entry)
        if not entries or entries[-1][1] <= since:
            break
    return list(found.values())
