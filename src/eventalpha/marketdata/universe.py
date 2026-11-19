"""Reviewed constituent snapshot. No automatic publisher access."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from eventalpha.schema import minute_universe_members

BENCHMARKS = {"SPY", "QQQ", "SMH"}


def _symbols(values: list[str], lower: int, upper: int) -> list[str]:
    symbols = sorted({value.strip().upper().replace(".", "-") for value in values})
    if not lower <= len(symbols) <= upper or any(not re.fullmatch(r"[A-Z][A-Z0-9-]{0,9}", s) for s in symbols):
        raise ValueError(f"Unexpected constituent list size or symbol format: {len(symbols)}")
    return symbols


def collection_symbols(engine: Engine, snapshot: Path, now: datetime) -> list[str]:
    """Use the reviewed, checked-in snapshot. No automated publisher requests."""
    data = json.loads(snapshot.read_text())
    observed = datetime.fromisoformat(data["fetched_at"])
    members = {
        "nasdaq100": _symbols(data["nasdaq100"], 95, 110),
        "sp500": _symbols(data["sp500"], 490, 520),
    }
    rows = [
        {"index_name": name, "symbol": symbol, "fetched_at": observed}
        for name, symbols in members.items()
        for symbol in symbols
    ]
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(58421902)"))
        stored = conn.execute(
            select(
                func.min(minute_universe_members.c.fetched_at),
                func.max(minute_universe_members.c.fetched_at),
                func.count(),
            ).select_from(minute_universe_members)
        ).one()
        if stored != (observed, observed, len(rows)):
            conn.execute(delete(minute_universe_members))
            conn.execute(insert(minute_universe_members), rows)
    return sorted(set().union(*members.values(), BENCHMARKS))
