"""Symbols the minute-candle collector covers: every index member plus the benchmark ETFs."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

from eventalpha.index_members import load_snapshot, sync_members

BENCHMARKS = {"SPY", "QQQ", "SMH", "DIA"}


def collection_symbols(engine: Engine, snapshot: Path) -> list[str]:
    """Read the reviewed snapshot (no publisher requests) and mirror it into `index_members`."""
    members = load_snapshot(snapshot)
    sync_members(engine, members)
    return sorted(set(members.all_symbols()) | BENCHMARKS)
