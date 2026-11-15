"""
### Trading-day signals → Telegram

* **signal_spx_overnight:** 15 min before the SPX session ends (16:45 ET, or 13:45 on 13:00
  early-close days). Market-wide read for the overnight SPX session: top-50 news weighted by
  index weight, breadth of company news, next session's macro calendar and earnings, close.
* **signal_premarket:** 09:15 ET. Ticker-specific: companies with material news since the last
  close, insider buying, today's earnings and macro releases (with CPI surprise vs the Cleveland
  Fed nowcast on CPI days), premarket moves.

Signals run on the clock and never wait for inputs: each alert states how fresh every input
was. Rows land in `signals`, so every alert can be replayed and evaluated later.
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
    scheduled_local_time,
    settings,
    table_asset,
    trading_session_gate,
    universe,
)

# 15 min before the SPX session ends, which is 1 h after the equity close (17:00 / 14:00).
SPX_OFFSET = timedelta(hours=1) - timedelta(minutes=15)
SIGNALS = table_asset("signals")
PARAMS = {
    "force": Param(False, type="boolean"),
    "as_of": Param("", type="string", description="Replay as of this time, e.g. 2026-11-13T16:45:00-05:00"),
}


def _publish(signal) -> dict:
    from eventalpha.alerts import send_telegram
    from eventalpha.db import upsert_rows
    from eventalpha.signals.render import render_premarket, render_spx_overnight

    text = render_spx_overnight(signal) if signal.signal_type == "spx_overnight" else render_premarket(signal)
    # The exact channel message is stored with the signal; the web UI's channel preview shows it.
    upsert_rows(engine(), "signals", [signal.row() | {"message": text}], key=["signal_type", "session_date"])
    print(text)
    send_telegram(settings(), text)
    if settings().redis_url:
        import redis

        from eventalpha.event_stream import feed_fields, publish_feed_items

        title = "SPX overnight signal" if signal.signal_type == "spx_overnight" else "Premarket signal"
        with redis.Redis.from_url(settings().redis_url, decode_responses=True) as r:
            publish_feed_items(
                r,
                [
                    feed_fields(
                        "signal",
                        f"signal:{signal.signal_type}:{signal.session_date}",
                        title,
                        impact="high",
                        label="TRADING SIGNAL",
                        occurred_at=signal.generated_at.isoformat(),
                    )
                ],
            )
    return {"score": signal.score, "confidence": signal.confidence}


@dag(
    schedule=MultipleCronTriggerTimetable("45 13 * * 1-5", "45 16 * * 1-5", timezone=NY),
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS | {"retries": 1, "retry_delay": timedelta(minutes=1)},
    params=PARAMS,
    tags=["signal"],
    doc_md=__doc__,
)
def signal_spx_overnight():
    @task.short_circuit
    def due_now(**context) -> bool:
        return trading_session_gate(context, close_offset=SPX_OFFSET)

    @task(outlets=[SIGNALS])
    def build_and_send(**context) -> dict:
        from sqlalchemy import text

        from eventalpha.sessions import get_session, previous_session, session_close_at
        from eventalpha.signals.build import build_spx_overnight

        now = scheduled_local_time(context)
        prev = previous_session(engine(), now.date())
        window_start = session_close_at(prev) + SPX_OFFSET if prev else now - timedelta(days=1)
        with engine().connect() as conn:
            nxt = conn.execute(
                text("SELECT min(day) FROM market_sessions WHERE day > :d AND is_open"), {"d": now.date()}
            ).scalar()
        assert get_session(engine(), now.date()) is not None
        return _publish(build_spx_overnight(engine(), universe(), now.date(), window_start, now, nxt))

    due_now() >> build_and_send()


@dag(
    schedule="15 9 * * 1-5",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS | {"retries": 1, "retry_delay": timedelta(minutes=1)},
    params=PARAMS,
    tags=["signal"],
    doc_md=__doc__,
)
def signal_premarket():
    @task.short_circuit
    def is_trading_day(**context) -> bool:
        return trading_session_gate(context)

    @task(outlets=[SIGNALS])
    def build_and_send(**context) -> dict:
        from eventalpha.sessions import previous_session, session_close_at
        from eventalpha.signals.build import build_premarket

        now = scheduled_local_time(context)
        prev = previous_session(engine(), now.date())
        window_start = session_close_at(prev) if prev else now - timedelta(days=1)
        return _publish(build_premarket(engine(), universe(), now.date(), window_start, now))

    is_trading_day() >> build_and_send()


signal_spx_overnight()
signal_premarket()
