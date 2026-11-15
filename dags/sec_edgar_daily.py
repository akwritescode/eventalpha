"""
### SEC EDGAR daily DAGs, one per filing family (generated)

`business day? ─► wait for daily index ─► list filings ─► fetch[batch] ─► publish`

| DAG | Forms | Lands in |
|---|---|---|
| `sec_events_daily` | 8-K, 6-K, Schedule 13D(/A), S-1, 424B4, 424B5 | `articles` (then classified) |
| `sec_insider_daily` | Form 4(/A) | `insider_transactions` |
| `sec_holdings_daily` | 13F-HR(/A) | `institutional_filings`, `institutional_holdings` |
| `sec_periodic_daily` | 10-K, 10-Q (+/A) | `report_sections`, `financial_facts` |

* **One DAG per family, from one file** (dynamic DAG generation): each can be backfilled,
  paused, or retried on its own. Two years of 13F history shouldn't re-fetch every 8-K.
* **Data interval = filing date** (New York time): the run for 2026-11-13 always fetches that day's filings,
  so `airflow backfill create` rebuilds any range.
* **Sensor in reschedule mode** waits for SEC's evening index without holding a worker slot;
  `soft_fail` turns holidays (no index, ever) into skips.
* **Pool `sec_edgar`** is shared by all four DAGs, so together they stay under SEC's 10 req/s.
  Each family has a `priority_weight` (events 40 > insider 30 > periodic 20 > holdings 10), so
  on heavy days trading-relevant batches take free slots before 13F holdings.
* Every filing gets a `sec_filings` ledger row: loaded / skipped / failed, with the reason.
"""

from __future__ import annotations

from datetime import date, timedelta

from airflow.sdk import PokeReturnValue, dag, get_current_context, task
from airflow.timetables.interval import CronDataIntervalTimetable
from eventalpha_common import DEFAULT_ARGS, FAMILY_ASSETS, NY, START_DATE, chunk, engine, settings

from eventalpha.sec.registry import FAMILIES, Family  # stdlib-only: keeps DAG parsing fast


def _client():
    from eventalpha.sec.client import RateLimitedClient

    s = settings()
    return RateLimitedClient(s.sec_user_agent, s.sec_requests_per_second)


def build(family: Family):
    @dag(
        dag_id=f"sec_{family.name}_daily",
        description=family.description,
        # Interval [D 01:00 ET, D+1 01:00 ET) runs at D+1 01:00 ET, after SEC posts day D's
        # index (~22:00 ET). The interval's start date is the filing date.
        schedule=CronDataIntervalTimetable("0 1 * * *", timezone=NY),
        start_date=START_DATE,
        catchup=False,
        max_active_runs=2,
        default_args=DEFAULT_ARGS,
        tags=["ingest", "sec", family.name],
        doc_md=__doc__,
    )
    def sec_family_daily():
        @task
        def filing_date() -> str:
            start = get_current_context()["data_interval_start"]  # delivered in UTC
            return start.in_timezone(NY).date().isoformat()

        @task.short_circuit
        def is_business_day(d: str) -> bool:
            return date.fromisoformat(d).weekday() < 5

        @task.sensor(poke_interval=1800, timeout=10 * 3600, mode="reschedule", soft_fail=True)
        def wait_for_daily_index(d: str) -> PokeReturnValue:
            from eventalpha.sec.index import fetch_daily_index

            with _client() as client:
                return PokeReturnValue(is_done=fetch_daily_index(client, date.fromisoformat(d)) is not None)

        # weight_rule="absolute": the priority is the family's own, not summed over downstream tasks.
        @task(pool="sec_edgar", priority_weight=family.priority, weight_rule="absolute")
        def list_filings(d: str) -> list[list[dict]]:
            from eventalpha.db import load_cik_map
            from eventalpha.landing import write_jsonl
            from eventalpha.sec.index import fetch_daily_index, select_filings

            day = date.fromisoformat(d)
            cik_map = load_cik_map(engine())
            if family.universe_only and not cik_map:
                raise RuntimeError("ticker_universe is empty: run the sec_ticker_universe DAG first")
            with _client() as client:
                entries = fetch_daily_index(client, day) or []
            filings = select_filings(entries, family.forms, set(cik_map) if family.universe_only else None)
            records = [f.to_dict() for f in filings]
            write_jsonl(settings().raw_data_dir, f"sec_index_{family.name}", day, "index", records,
                        bucket=settings().raw_bucket)
            print(f"{len(entries)} filings on {d}; {len(filings)} in family {family.name}")
            return chunk(records, family.batch_size)

        @task(pool="sec_edgar", max_active_tis_per_dagrun=2, execution_timeout=timedelta(minutes=45),
              priority_weight=family.priority, weight_rule="absolute")
        def fetch(batch: list[dict]) -> dict:
            from eventalpha.db import load_cik_map
            from eventalpha.sec.families import process_batch
            from eventalpha.sec.index import IndexEntry

            with _client() as client:
                return process_batch(
                    family, client, engine(), [IndexEntry.from_dict(r) for r in batch], load_cik_map(engine())
                )

        @task(outlets=FAMILY_ASSETS[family.name])
        def publish(results: list[dict]) -> dict:
            totals = {k: sum(r[k] for r in results) for k in ("loaded", "skipped", "failed", "rows")}
            print(totals)
            if family.name == "events":  # dead-man's switch: alert if a business day passes without this
                from eventalpha.alerts import ping_healthcheck

                ping_healthcheck(settings())
            return totals

        d = filing_date()
        index_ready = wait_for_daily_index(d)
        batches = list_filings(d)
        is_business_day(d) >> index_ready >> batches
        publish(fetch.expand(batch=batches))

    return sec_family_daily()


for _family in FAMILIES.values():
    build(_family)
