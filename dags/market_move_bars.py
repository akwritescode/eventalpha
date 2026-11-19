"""Collect completed regular-session minute candles for the Nasdaq-100 / S&P 500 union."""

from __future__ import annotations

from datetime import timedelta

from airflow.sdk import dag, task
from eventalpha_common import DEFAULT_ARGS, START_DATE, chunk, engine, market_data, settings


@dag(
    schedule="*/15 9-16 * * 1-5",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["market"],
    doc_md=__doc__,
)
def market_move_bars():
    @task
    def plan() -> list[list[str]]:
        import os
        from datetime import UTC, datetime
        from pathlib import Path

        from eventalpha.marketdata.storage import ensure_partitions
        from eventalpha.marketdata.universe import collection_symbols

        if not settings().tradier_broker_key:
            return []
        now = datetime.now(UTC)
        db = engine()
        feeds_config = os.environ.get("FEEDS_CONFIG")
        if not feeds_config:
            raise ValueError("FEEDS_CONFIG must point to the feed configuration file")
        symbols = collection_symbols(db, Path(feeds_config).with_name("candle_universe.json"), now)
        ensure_partitions(db, now.date() - timedelta(days=8), now.date() + timedelta(days=7))
        return chunk(symbols, 25)

    @task(max_active_tis_per_dag=2, execution_timeout=timedelta(minutes=14))
    def collect(symbols: list[str]) -> dict:
        import time
        from dataclasses import asdict
        from datetime import UTC, datetime

        from sqlalchemy import func, select

        from eventalpha.marketdata.storage import store_bars
        from eventalpha.schema import price_bars_minute
        from eventalpha.signals.universe import tradier_symbol

        db = engine()
        end = datetime.now(UTC).replace(second=0, microsecond=0)
        floor = end - timedelta(days=8)
        provider = market_data()
        inserted = 0
        failed = []
        for symbol in symbols:
            began = time.monotonic()
            try:
                with db.connect() as conn:
                    latest = conn.scalar(
                        select(func.max(price_bars_minute.c.started_at)).where(price_bars_minute.c.symbol == symbol)
                    )
                # Recheck recent bars for holes, without re-fetching a whole day per ticker.
                start = max(floor, latest - timedelta(hours=1)) if latest else floor
                bars = provider.minute_bars(tradier_symbol(symbol), start, end)
                inserted += store_bars(db, [asdict(bar) | {"symbol": symbol} for bar in bars])
            except Exception:
                # Isolate malformed replies and database failures to this symbol.
                import logging

                logging.getLogger(__name__).exception("Minute candle collection failed for %s", symbol)
                failed.append(symbol)
            finally:
                # Two workers, each <=40 symbol requests/minute, leaving headroom for
                # the existing quote/signal jobs sharing the brokerage key.
                time.sleep(max(0, 1.5 - (time.monotonic() - began)))
        if failed:
            raise RuntimeError(f"Minute candle requests failed for: {', '.join(failed)}")
        return {"symbols": len(symbols), "inserted": inserted}

    collect.expand(symbols=plan())


market_move_bars()
