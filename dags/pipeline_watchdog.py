"""
### Pipeline watchdog, hourly

Alerts the Telegram ops chat (`TELEGRAM_OPS_CHAT_ID`) when a DAG is **paused** or a DAG file
**fails to import**. Neither one fails a task, so `on_failure_callback` never fires and the
data just stops (this is how the news feed sat empty until its DAG was unpaused).

* Reads the Airflow REST API (`/api/v2/dags`, `/api/v2/importErrors`): task code has no
  metadata-DB access in Airflow 3, so the `airflow` CLI fails inside a task. With a login
  configured it authenticates as `admin` with `AIRFLOW_ADMIN_PASSWORD`.
* Each problem is repeated at most every 12 h; a fixed one is forgotten, so it alerts again
  right away if it recurs.
* Starts unpaused (`is_paused_upon_creation=False`): a watchdog that needs unpausing would
  have the same blind spot. If it's paused by hand, nothing watches it; the healthchecks.io
  dead-man's switch is the backstop for that.
"""

from __future__ import annotations

import os

from airflow.sdk import dag, task
from eventalpha_common import DEFAULT_ARGS, START_DATE, settings

# DAGs paused on purpose, never reported. Empty: every DAG in this repo should be running.
IGNORE: tuple[str, ...] = ()


@dag(
    schedule="5 * * * *",
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args=DEFAULT_ARGS,
    tags=["ops"],
    doc_md=__doc__,
)
def pipeline_watchdog():
    @task
    def check() -> dict:
        import httpx

        from eventalpha import watchdog
        from eventalpha.alerts import send_telegram

        # Task code has no metadata-DB access in Airflow 3 (the CLI fails inside a task),
        # so ask the API server. Locally every user is admin; with a login, use the admin password.
        base = os.environ.get("AIRFLOW_API_URL", "http://airflow-apiserver:8080").rstrip("/")
        with httpx.Client(base_url=base, timeout=20) as api:
            if password := os.environ.get("AIRFLOW_ADMIN_PASSWORD"):
                token = api.post("/auth/token", json={"username": "admin", "password": password})
                token.raise_for_status()
                api.headers["Authorization"] = f"Bearer {token.json()['access_token']}"
            dags = api.get("/api/v2/dags", params={"limit": 1000}).raise_for_status().json()["dags"]
            errors = api.get("/api/v2/importErrors", params={"limit": 1000}).raise_for_status().json()

        paused = watchdog.paused_dags(dags, ignore=IGNORE)
        broken = watchdog.broken_files(errors.get("import_errors", []))

        if settings().redis_url:  # report each problem once per 12 h
            import redis

            with redis.Redis.from_url(settings().redis_url, decode_responses=True) as r:
                watchdog.clear(r, "paused", [d["dag_id"] for d in dags if d["dag_id"] not in paused])
                watchdog.forget_resolved(r, "broken", broken)  # fixed files drop off the error list
                new_paused = watchdog.due(r, "paused", paused)
                new_broken = watchdog.due(r, "broken", broken)
        else:
            new_paused, new_broken = paused, broken

        text = watchdog.format_alert(new_paused, new_broken)
        sent = bool(text) and send_telegram(settings(), text, ops=True)  # ops chat, never the channel
        if text and not sent and settings().redis_url:  # not delivered: try again next hour
            with redis.Redis.from_url(settings().redis_url, decode_responses=True) as r:
                watchdog.clear(r, "paused", new_paused)
                watchdog.clear(r, "broken", new_broken)
        return {"paused": paused, "broken": broken, "alerted": sent}

    check()


pipeline_watchdog()
