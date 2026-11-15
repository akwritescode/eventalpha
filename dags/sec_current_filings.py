"""
### SEC filings within minutes, from EDGAR's "latest filings" feed

Every 15 min from 06:00 to 20:00 ET on weekdays, so after-hours and pre-market 8-Ks reach the
16:45 and 09:15 signals. Filings are processed by the same events pipeline as the nightly
`sec_events_daily` run and keyed on accession number, so the nightly run only fills gaps.
Filings already in the `sec_filings` ledger are skipped.
"""

from __future__ import annotations

from datetime import timedelta

from airflow.sdk import dag, task
from eventalpha_common import ARTICLES, DEFAULT_ARGS, START_DATE, engine, settings

FORMS = ("8-K", "6-K", "SCHEDULE 13D", "424B5", "424B4", "S-1")
LOOKBACK = timedelta(hours=3)  # overlap covers missed runs; the ledger makes reprocessing a no-op


@dag(schedule="*/15 6-20 * * 1-5", start_date=START_DATE, catchup=False, max_active_runs=1,
     default_args=DEFAULT_ARGS | {"retries": 1}, tags=["ingest", "sec", "intraday"], doc_md=__doc__)
def sec_current_filings():
    # Highest priority in the shared SEC pool: these feed the 16:45 and 09:15 alerts.
    @task(pool="sec_edgar", outlets=[ARTICLES], priority_weight=100, weight_rule="absolute")
    def fetch_and_load() -> dict:
        import pendulum
        from sqlalchemy import select

        from eventalpha.db import load_cik_map
        from eventalpha.schema import sec_filings
        from eventalpha.sec.client import RateLimitedClient
        from eventalpha.sec.current import fetch_current
        from eventalpha.sec.families import process_batch
        from eventalpha.sec.index import select_filings
        from eventalpha.sec.registry import FAMILIES

        s = settings()
        since = pendulum.now("UTC") - LOOKBACK
        family = FAMILIES["events"]
        cik_map = load_cik_map(engine())
        with RateLimitedClient(s.sec_user_agent, s.sec_requests_per_second) as client:
            entries = [e for form in FORMS for e in fetch_current(client, form, since)]
            entries = [e for e in entries if e.form_type in family.forms]
            selected = select_filings(entries, family.forms, set(cik_map))
            with engine().connect() as conn:
                done = set(conn.execute(select(sec_filings.c.accession)
                                        .where(sec_filings.c.accession.in_([e.accession for e in selected])))
                           .scalars())
            todo = [e for e in selected if e.accession not in done]
            result = process_batch(family, client, engine(), todo, cik_map) if todo else {"loaded": 0}
        print(f"{len(entries)} in feed, {len(selected)} listed companies, {len(todo)} new → {result}")
        return result

    fetch_and_load()


sec_current_filings()
