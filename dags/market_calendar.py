"""
### Exchange session calendar

Loads this month and the next two from the market data provider (holidays, 13:00 early
closes) into `market_sessions`. Every trading-day check reads that table.
"""

from __future__ import annotations

from airflow.sdk import dag, task
from eventalpha_common import DEFAULT_ARGS, START_DATE, engine, market_data


@dag(schedule="15 0 * * *", start_date=START_DATE, catchup=False, default_args=DEFAULT_ARGS,
     tags=["reference", "market"], doc_md=__doc__)
def market_calendar():
    @task
    def refresh() -> int:
        import pendulum

        from eventalpha.sessions import refresh_sessions

        return refresh_sessions(engine(), market_data(), pendulum.now("America/New_York").date())

    refresh()


market_calendar()
