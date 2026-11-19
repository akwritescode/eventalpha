"""Refresh config/index_members.json: S&P 500, Nasdaq-100 and Dow Jones Industrial Average members.

    uv run python scripts/refresh_index_members.py           # fetch, report changes, write
    uv run python scripts/refresh_index_members.py --check   # fetch and report; exit 1 if changed

When to run: after each quarterly rebalance (S&P and Dow Jones: effective after the third Friday
of March, June, September and December; Nasdaq-100: the annual December reconstitution plus the
same quarterly reviews). Also after an ad-hoc change such as an acquisition removing a member.
The pipeline watchdog warns once the snapshot is older than a quarter.

Source: the constituents tables on Wikipedia's list pages, read through the MediaWiki API
(which permits automated access with a descriptive User-Agent; set WIKIMEDIA_USER_AGENT, or
SEC_USER_AGENT is reused). Membership is a public fact, but a wiki page can be wrong or
mid-edit, so the script never updates the pipeline by itself: it validates list sizes and symbol
formats, prints what was added and removed per index, and writes the file for review in a pull
request. Each index records the exact page revision it came from.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eventalpha.index_members import INDEXES, LABELS, Snapshot, diff, load_snapshot, normalize  # noqa: E402

API = "https://en.wikipedia.org/w/api.php"
PAGES = {
    "sp500": "List of S&P 500 companies",
    "nasdaq100": "List of NASDAQ-100 companies",
    "dow30": "List of Dow Jones Industrial Average companies",
}
SYMBOL_HEADERS = {"symbol", "ticker"}
FOOTNOTE = re.compile(r"\[[^\]]*\]")


def parse_constituents(page_html: str) -> list[str]:
    """Symbols from the page's `constituents` table (its Symbol or Ticker column)."""
    doc = html.fromstring(page_html)
    tables = doc.xpath('//table[@id="constituents"]')
    if len(tables) != 1:
        raise ValueError(f"expected one table with id=constituents, found {len(tables)}")
    rows = tables[0].xpath(".//tr")
    headers = [FOOTNOTE.sub("", h.text_content()).strip().lower() for h in rows[0].xpath("./th|./td")]
    column = next((i for i, h in enumerate(headers) if h in SYMBOL_HEADERS), None)
    if column is None:
        raise ValueError(f"no Symbol/Ticker column in {headers}")
    symbols = []
    for row in rows[1:]:
        cells = row.xpath("./th|./td")  # some tables put the company name in a row-header <th>
        if len(cells) > column:
            symbols.append(FOOTNOTE.sub("", cells[column].text_content()).strip())
    return symbols


def fetch_page(client: httpx.Client, title: str) -> tuple[str, int]:
    """(rendered HTML, revision id). Backs off on 429 as Wikimedia's rate-limit policy asks."""
    params = {"action": "parse", "page": title, "prop": "text|revid", "redirects": 1}
    params |= {"format": "json", "formatversion": 2}
    for attempt in range(4):
        resp = client.get(API, params=params)
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After") or 30 * (attempt + 1)))
            continue
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise ValueError(f"{title}: {body['error'].get('info')}")
        return body["parse"]["text"], int(body["parse"]["revid"])
    raise RuntimeError(f"{title}: still rate limited after retries")


def render(snapshot: Snapshot) -> str:
    data = {
        "as_of": snapshot.as_of.isoformat(),
        "indexes": {
            name: {"label": LABELS[name], "source": snapshot.sources[name], "symbols": list(snapshot.members[name])}
            for name in INDEXES
        },
    }
    return json.dumps(data, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "config/index_members.json")
    parser.add_argument("--check", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    agent = os.environ.get("WIKIMEDIA_USER_AGENT") or os.environ.get("SEC_USER_AGENT")
    if not agent:
        parser.error("set WIKIMEDIA_USER_AGENT (e.g. 'EventAlpha index refresh (you@example.com)')")

    members, sources = {}, {}
    with httpx.Client(headers={"User-Agent": agent}, timeout=30) as client:
        for name, title in PAGES.items():
            page, revid = fetch_page(client, title)
            members[name] = normalize(parse_constituents(page), name)
            sources[name] = f"https://en.wikipedia.org/w/index.php?title={quote(title.replace(' ', '_'))}&oldid={revid}"
    fresh = Snapshot(datetime.now(UTC).replace(microsecond=0), members, sources)

    old = load_snapshot(args.out) if args.out.exists() else None
    if old:
        changes = diff(old, fresh)
        changed = any(c["added"] or c["removed"] for c in changes.values())
        for name, c in changes.items():
            print(
                f"{LABELS[name]:30} {len(members[name]):4} symbols"
                f"   added {c['added'] or '-'}   removed {c['removed'] or '-'}"
            )
    else:
        changed = True
        for name in INDEXES:
            print(f"{LABELS[name]:30} {len(members[name]):4} symbols (new snapshot)")
    union = fresh.all_symbols()
    print(f"{'Union (deduplicated)':30} {len(union):4} symbols")

    if args.check:
        return 1 if changed else 0
    if not changed and old:
        print("No membership changes; snapshot left as is.")
        return 0
    args.out.write_text(render(fresh))
    print(f"wrote {args.out.relative_to(ROOT)}: review the changes above in a pull request")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
