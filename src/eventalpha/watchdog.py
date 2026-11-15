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
from typing import Any

REPEAT_HOURS = 12
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


def due(client, kind: str, names: Sequence[str]) -> list[str]:
    """The names not reported in the last REPEAT_HOURS; marks them reported."""
    return [n for n in names if client.set(_KEY.format(kind=kind, name=n), "1", nx=True, ex=REPEAT_HOURS * 3600)]


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


def format_alert(paused: Sequence[str], broken: Sequence[str]) -> str | None:
    if not (paused or broken):
        return None
    lines = ["⚠️ <b>EventAlpha pipeline check</b>"]
    if paused:
        lines.append("Paused, not collecting data:")
        lines += [f"• <code>{html.escape(d)}</code>" for d in paused]
    if broken:
        lines.append("Failing to load (DAG missing from Airflow):")
        lines += [f"• <code>{html.escape(f)}</code>" for f in broken]
    return "\n".join(lines)
