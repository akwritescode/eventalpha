"""
### Listed-company reference data

SEC's `company_tickers.json` (ticker, CIK, name) loaded into `ticker_universe`, daily
before the filing DAGs run. Filings are matched to tickers through CIK.

Known limitation: this is *today's* list, so a backfill over old dates misses companies
that have since delisted (survivorship bias). A point-in-time universe is future work.
"""

from __future__ import annotations

from airflow.sdk import dag, task
from eventalpha_common import DEFAULT_ARGS, START_DATE, TICKER_UNIVERSE, engine, settings


@dag(
    schedule="30 0 * * *",  # 00:30 ET, before the 01:00 ET SEC DAGs
    start_date=START_DATE,
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
