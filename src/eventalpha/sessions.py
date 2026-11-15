"""Trading-day and session-time logic, from the provider's exchange calendar.

The two signals run at fixed offsets from the session's end, so on 13:00 early-close days
they move with it (e.g. 16:45 → 13:45). DAGs are scheduled at both candidate times and this
module decides which run is the real one.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, select

from eventalpha.db import upsert_rows
from eventalpha.marketdata.base import MarketDataProvider, SessionDay
from eventalpha.schema import market_sessions

NY = ZoneInfo("America/New_York")
NORMAL_CLOSE = time(16, 0)


def refresh_sessions(engine: Engine, provider: MarketDataProvider, today: date, months_ahead: int = 2) -> int:
    rows = []
    y, m = today.year, today.month
    for _ in range(months_ahead + 1):
        if y > today.year:
            break  # Tradier only serves the current year; January loads once the year turns
        for d in provider.session_calendar(y, m):
            rows.append(
                {
                    "day": d.day,
                    "is_open": d.is_open,
                    "open_time": d.open_time,
                    "close_time": d.close_time,
                    "description": d.description,
                    "source": provider.name,
                }
            )
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return upsert_rows(engine, "market_sessions", rows, key=["day"])


def get_session(engine: Engine, day: date) -> SessionDay | None:
    with engine.connect() as conn:
        r = conn.execute(select(market_sessions).where(market_sessions.c.day == day)).first()
    if r is None:
        return None
    return SessionDay(r.day, r.is_open, r.open_time, r.close_time, r.description)


def previous_session(engine: Engine, day: date) -> SessionDay | None:
    with engine.connect() as conn:
        r = conn.execute(
            select(market_sessions)
            .where(market_sessions.c.day < day, market_sessions.c.is_open)
            .order_by(market_sessions.c.day.desc())
            .limit(1)
        ).first()
    return SessionDay(r.day, r.is_open, r.open_time, r.close_time, r.description) if r else None


def close_relative_due(session: SessionDay | None, scheduled_local: time, offset_from_close: timedelta) -> bool:
    """True if this run (scheduled at `scheduled_local` NY time) is the one that should fire:
    the market is open that day and the run time equals that day's close + offset."""
    if session is None or not session.is_open or session.close_time is None:
        return False
    target = (datetime.combine(session.day, session.close_time) + offset_from_close).time()
    return target == scheduled_local


def session_close_at(session: SessionDay) -> datetime:
    return datetime.combine(session.day, session.close_time or NORMAL_CLOSE, tzinfo=NY)
