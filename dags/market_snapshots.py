"""
### Point-in-time market snapshots for the signals

* **premarket** at 09:10 ET on trading days, feeding the 09:15 signal.
* **close** 35 min after the session closes (16:35, or 13:35 on early-close days), feeding the
  signal 15 min before the SPX session ends. Also stores the day's final daily bars.

Each snapshot keeps the exact quotes a signal saw, so any signal can be replayed later.
"""

from __future__ import annotations

from datetime import timedelta

from airflow.sdk import Param, dag, task
from airflow.timetables.trigger import MultipleCronTriggerTimetable
from eventalpha_common import (
    DEFAULT_ARGS,
    NY,
    START_DATE,
    engine,
    market_data,
    scheduled_local_time,
    table_asset,
    trading_session_gate,
    universe,
)

CLOSE_OFFSET = timedelta(minutes=35)


def _symbols() -> list[str]:
    from eventalpha.signals.universe import tradier_symbol

    u = universe()
    return list(u.context_symbols) + [tradier_symbol(t) for c in u.companies for t in c.tickers]


def _store(kind: str, context) -> int:
    import pendulum

    from eventalpha.db import upsert_rows

    session_date = scheduled_local_time(context).date()
    now = pendulum.now(NY)
    rows = [{"session_date": session_date, "kind": kind, "symbol": q.symbol, "captured_at": now, "last": q.last,
             "prev_close": q.prev_close, "change_pct": q.change_pct, "bid": q.bid, "ask": q.ask,
             "volume": q.volume, "trade_date": q.trade_date} for q in market_data().quotes(_symbols())]
    return upsert_rows(engine(), "market_snapshots", rows, key=["session_date", "kind", "symbol"])


@dag(schedule="10 9 * * 1-5", start_date=START_DATE, catchup=False, default_args=DEFAULT_ARGS,
     params={"force": Param(False, type="boolean")}, tags=["market"], doc_md=__doc__)
def market_snapshot_premarket():
    @task.short_circuit
    def is_trading_day(**context) -> bool:
        return trading_session_gate(context)

    @task(outlets=[table_asset("market_snapshots")])
    def snapshot(**context) -> int:
        return _store("premarket", context)

    is_trading_day() >> snapshot()


@dag(schedule=MultipleCronTriggerTimetable("35 13 * * 1-5", "35 16 * * 1-5", timezone=NY), start_date=START_DATE,
     catchup=False, default_args=DEFAULT_ARGS, params={"force": Param(False, type="boolean")},
     tags=["market"], doc_md=__doc__)
def market_snapshot_close():
    @task.short_circuit
    def due_now(**context) -> bool:
        return trading_session_gate(context, close_offset=CLOSE_OFFSET)

    @task(outlets=[table_asset("market_snapshots")])
    def snapshot(**context) -> int:
        return _store("close", context)

    @task(outlets=[table_asset("price_bars_daily")])
    def daily_bars(**context) -> int:
        from eventalpha.db import upsert_rows

        day = scheduled_local_time(context).date()
        provider = market_data()
        rows = [{"symbol": b.symbol, "day": b.day, "open": b.open, "high": b.high, "low": b.low, "close": b.close,
                 "volume": b.volume, "source": provider.name}
                for sym in _symbols() for b in provider.daily_bars(sym, day - timedelta(days=7), day)]
        return upsert_rows(engine(), "price_bars_daily", rows, key=["symbol", "day"])

    due_now() >> [snapshot(), daily_bars()]


market_snapshot_premarket()
market_snapshot_close()
