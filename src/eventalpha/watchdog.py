"""Pipeline watchdog: catches the failures that never raise.

A failed task sends an alert through `on_failure_callback`, but a paused DAG or one that no
longer imports simply produces nothing, and nothing notices. The watchdog DAG reads Airflow's
DAG list and import errors and reports both.

Each problem is reported once per `REPEAT_HOURS` (Redis SET NX + TTL), so a DAG left paused
reminds you twice a day instead of every hour.
"""

from __future__ import annotations

import html
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

REPEAT_HOURS = 12
STALE_REPEAT_HOURS = 7 * 24  # a quarterly refresh is due, not an outage: remind weekly
# Index membership changes at the quarterly rebalances (March, June, September, December), so
# reviewed reference files older than a quarter plus a little slack are due for a refresh.
MAX_REFERENCE_AGE_DAYS = 100
_KEY = "eventalpha:watchdog:{kind}:{name}"


def paused_dags(dags: Iterable[Mapping[str, Any]], ignore: Iterable[str] = ()) -> list[str]:
    """dag_ids that are paused, from the `/api/v2/dags` rows."""
    skip = set(ignore)
    return sorted(d["dag_id"] for d in dags if _truthy(d.get("is_paused")) and d["dag_id"] not in skip)


def broken_files(import_errors: Iterable[Mapping[str, Any]]) -> list[str]:
    """DAG files that failed to import, from `/api/v2/importErrors`."""
    return sorted({e.get("filename") or e.get("filepath") or "?" for e in import_errors})


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def stale_references(as_of: Mapping[str, date], today: date, max_age_days: int = MAX_REFERENCE_AGE_DAYS) -> list[str]:
    """Reviewed reference files (index membership, SPX weights) older than `max_age_days`,
    as "<file> (as of <date>, <n> days)"; the date in the name makes a refreshed file a new item."""
    return sorted(
        f"{name} (as of {d.isoformat()}, {(today - d).days} days)"
        for name, d in as_of.items()
        if (today - d).days > max_age_days
    )


def due(client, kind: str, names: Sequence[str], hours: int = REPEAT_HOURS) -> list[str]:
    """The names not reported in the last `hours`; marks them reported."""
    return [n for n in names if client.set(_KEY.format(kind=kind, name=n), "1", nx=True, ex=hours * 3600)]


def clear(client, kind: str, healthy: Iterable[str]) -> None:
    """Forget resolved problems, so a DAG paused again later is reported right away."""
    keys = [_KEY.format(kind=kind, name=n) for n in healthy]
    if keys:
        client.delete(*keys)


def forget_resolved(client, kind: str, current: Iterable[str]) -> None:
    """Forget every reported `kind` problem that is no longer current. Unlike clear(), it
    doesn't need the healthy names: a fixed import error simply drops off the error list."""
    keep = {_KEY.format(kind=kind, name=n) for n in current}
    stale = [k for k in client.scan_iter(_KEY.format(kind=kind, name="*")) if k not in keep]
    if stale:
        client.delete(*stale)


def format_alert(paused: Sequence[str], broken: Sequence[str], stale: Sequence[str] = ()) -> str | None:
    if not (paused or broken or stale):
        return None
    lines = ["⚠️ <b>EventAlpha pipeline check</b>"]
    if paused:
        lines.append("Paused, not collecting data:")
        lines += [f"• <code>{html.escape(d)}</code>" for d in paused]
    if broken:
        lines.append("Failing to load (DAG missing from Airflow):")
        lines += [f"• <code>{html.escape(f)}</code>" for f in broken]
    if stale:
        lines.append("Reference data due for its quarterly refresh (see scripts/refresh_*.py):")
        lines += [f"• {html.escape(f)}" for f in stale]
    return "\n".join(lines)
