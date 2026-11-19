"""Index membership: S&P 500, Nasdaq-100 and Dow Jones Industrial Average constituents.

One reviewed snapshot (`config/index_members.json`) is the list of companies EventAlpha covers:
earnings dates, minute candles and index alerts all read it. It's refreshed by an operator
after each quarterly index rebalance (`scripts/refresh_index_members.py`) and reviewed in a pull
request, so a bad source page can never change membership on its own. Nothing in the pipeline
fetches membership at run time.

Symbols use SEC spelling (share classes with a hyphen: BRK-B). The three indexes overlap; each
keeps its own list, and `all_symbols` gives the deduplicated union.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from eventalpha.schema import index_members

# Accepted list sizes. Share classes count separately (GOOGL and GOOG), so the S&P 500 lists
# roughly 503 symbols and the Nasdaq-100 roughly 101. A size outside these bounds means the source
# page changed shape, not that the index did.
INDEXES: dict[str, tuple[int, int]] = {
    "sp500": (495, 515),
    "nasdaq100": (99, 106),
    "dow30": (30, 30),
}
LABELS = {"sp500": "S&P 500", "nasdaq100": "Nasdaq-100", "dow30": "Dow Jones Industrial Average"}
SYMBOL = re.compile(r"[A-Z][A-Z0-9-]{0,9}")
SYNC_LOCK = 58421902  # advisory lock id serialising snapshot loads


@dataclass(frozen=True)
class Snapshot:
    as_of: datetime
    members: dict[str, tuple[str, ...]]
    sources: dict[str, str]

    def all_symbols(self) -> list[str]:
        return sorted(set().union(*self.members.values()))


def normalize(values: list[str], index: str) -> tuple[str, ...]:
    """SEC spelling, deduplicated and sorted; rejects an implausible list outright."""
    symbols = sorted({v.strip().upper().replace(".", "-").replace("/", "-") for v in values if v.strip()})
    lower, upper = INDEXES[index]
    if not lower <= len(symbols) <= upper:
        raise ValueError(f"{LABELS[index]}: {len(symbols)} symbols, expected {lower}-{upper}")
    bad = [s for s in symbols if not SYMBOL.fullmatch(s)]
    if bad:
        raise ValueError(f"{LABELS[index]}: unexpected symbol format {bad[:5]}")
    return tuple(symbols)


def load_snapshot(path: Path) -> Snapshot:
    data = json.loads(path.read_text())
    as_of = datetime.fromisoformat(data["as_of"])
    if as_of.utcoffset() is None:
        raise ValueError("index_members.json: as_of must carry a UTC offset")
    indexes = data["indexes"]
    missing = set(INDEXES) - set(indexes)
    if missing:
        raise ValueError(f"index_members.json: missing {sorted(missing)}")
    return Snapshot(
        as_of=as_of,
        members={name: normalize(indexes[name]["symbols"], name) for name in INDEXES},
        sources={name: indexes[name]["source"] for name in INDEXES},
    )


def sync_members(engine: Engine, snapshot: Snapshot) -> bool:
    """Mirror the snapshot into `index_members` so SQL (API, alerts) can join on membership.
    Rewrites only when the snapshot changed; returns whether it did."""
    rows = [
        {"index_name": name, "symbol": symbol, "fetched_at": snapshot.as_of}
        for name, symbols in snapshot.members.items()
        for symbol in symbols
    ]
    with engine.begin() as conn:
        conn.execute(text(f"SELECT pg_advisory_xact_lock({SYNC_LOCK})"))
        stored = conn.execute(
            select(
                func.min(index_members.c.fetched_at), func.max(index_members.c.fetched_at), func.count()
            ).select_from(index_members)
        ).one()
        if tuple(stored) == (snapshot.as_of, snapshot.as_of, len(rows)):
            return False
        conn.execute(delete(index_members))
        conn.execute(insert(index_members), rows)
        return True


def diff(old: Snapshot, new: Snapshot) -> dict[str, dict[str, list[str]]]:
    """Per index: symbols added and removed between two snapshots (for the refresh report)."""
    return {
        name: {
            "added": sorted(set(new.members[name]) - set(old.members[name])),
            "removed": sorted(set(old.members[name]) - set(new.members[name])),
        }
        for name in INDEXES
    }
