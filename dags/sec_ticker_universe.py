"""
### Listed-company reference data

SEC's `company_tickers.json` (ticker, CIK, name) loaded into `ticker_universe`, daily
before the filing DAGs run. Filings are matched to tickers through CIK.

Known limitation: this is *today's* list, so a backfill over old dates misses companies
that have since delisted (survivorship bias). A point-in-time universe is future work.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task
from eventalpha_common import DEFAULT_ARGS, TICKER_UNIVERSE, engine, settings


@dag(
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["reference", "sec"],
    doc_md=__doc__,
)
def sec_ticker_universe():
    @task(pool="sec_edgar", outlets=[TICKER_UNIVERSE])
    def refresh() -> int:
        from eventalpha.db import upsert_ticker_universe
        from eventalpha.sec.client import RateLimitedClient
        from eventalpha.sec.index import fetch_company_tickers

        s = settings()
        with RateLimitedClient(s.sec_user_agent, s.sec_requests_per_second) as client:
            rows = fetch_company_tickers(client)
        return upsert_ticker_universe(engine(), rows)

    refresh()


sec_ticker_universe()
