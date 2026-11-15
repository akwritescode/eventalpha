"""
### Macro data: FRED series and BLS series, plus Cleveland Fed inflation nowcasts

* **macro_data** runs at 08:40 ET (right after 08:30 BLS releases, so the 09:15 signal sees
  them) and 18:00 ET (FRED publishes most daily market series in the evening).
* **inflation_nowcast** runs at 10:30 ET, after the Cleveland Fed's ~10:00 daily update.
"""

from __future__ import annotations

from datetime import timedelta

from airflow.sdk import dag, task
from airflow.timetables.trigger import MultipleCronTriggerTimetable
from eventalpha_common import DEFAULT_ARGS, NY, START_DATE, engine, settings, table_asset


@dag(
    schedule=MultipleCronTriggerTimetable("40 8 * * 1-5", "0 18 * * 1-5", timezone=NY),
    start_date=START_DATE,
    catchup=False,
    default_args=DEFAULT_ARGS,
    max_active_runs=1,
    tags=["macro"],
    doc_md=__doc__,
)
def macro_data():
    @task(outlets=[table_asset("macro_observations")])
    def fred_series() -> int:
        import pendulum

        from eventalpha.db import upsert_rows
        from eventalpha.macro.fred import SERIES, FredClient

        client = FredClient(settings().fred_api_key)
        start = pendulum.now(NY).date() - timedelta(days=400)  # a year of history; upserts are idempotent
        rows = [
            {"source": "fred", "series_id": o.series_id, "period": o.day, "value": o.value, "preliminary": False}
            for sid in SERIES
            for o in client.observations(sid, start)
        ]
        return upsert_rows(engine(), "macro_observations", rows, key=["source", "series_id", "period"])

    @task(outlets=[table_asset("macro_observations")])
    def bls_series() -> int:
        from datetime import date

        import pendulum

        from eventalpha.db import upsert_rows
        from eventalpha.macro.bls import SERIES, BlsClient

        s = settings()
        year = pendulum.now(NY).year
        rows = []
        for o in BlsClient(s.bls_api_key, s.sec_user_agent).series(list(SERIES), year - 1, year):
            if o.period.startswith("M") and o.period != "M13":  # monthly values; M13 = annual average
                rows.append(
                    {
                        "source": "bls",
                        "series_id": o.series_id,
                        "period": date(o.year, int(o.period[1:]), 1),
                        "value": o.value,
                        "preliminary": o.preliminary,
                    }
                )
        return upsert_rows(engine(), "macro_observations", rows, key=["source", "series_id", "period"])

    @task(trigger_rule="all_done")
    def announce_releases() -> int:
        """Push today's already-released economic events to the web UI's stream (once each).
        Runs after the data tasks, so the card the UI fetches already has its numbers."""
        import pendulum
        from sqlalchemy import text

        if not settings().redis_url:
            return 0
        import redis

        from eventalpha.event_stream import feed_fields, publish_feed_items

        with engine().connect() as conn:
            rows = conn.execute(
                text("""
                SELECT source, event_key, title, coalesce(scheduled_at,
                       (event_date + time '08:30') AT TIME ZONE 'America/New_York') AS at
                FROM econ_events
                WHERE event_date = :today AND (importance = 'high' OR title LIKE 'Producer Price Index%')
                  AND coalesce(scheduled_at, (event_date + time '08:30') AT TIME ZONE 'America/New_York') <= now()
            """),
                {"today": pendulum.now(NY).date()},
            ).all()
        items = [
            feed_fields(
                "macro",
                f"macro:{r.source}:{r.event_key}",
                r.title,
                impact="high",
                label="MACRO",
                occurred_at=r.at.isoformat(),
            )
            for r in rows
        ]
        with redis.Redis.from_url(settings().redis_url, decode_responses=True) as client:
            return publish_feed_items(client, items)

    [fred_series(), bls_series()] >> announce_releases()


@dag(
    schedule="30 10 * * 1-5",
    start_date=START_DATE,
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["macro"],
    doc_md=__doc__,
)
def inflation_nowcast():
    @task(outlets=[table_asset("inflation_nowcasts")])
    def fetch() -> int:
        from eventalpha.db import upsert_rows
        from eventalpha.macro.nowcast import fetch_nowcasts

        rows = fetch_nowcasts(settings().sec_user_agent)
        return upsert_rows(engine(), "inflation_nowcasts", rows, key=["horizon", "target_period", "measure", "vintage"])

    fetch()


macro_data()
inflation_nowcast()
