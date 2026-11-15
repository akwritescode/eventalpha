"""
### Nightly housekeeping

* `backup_warehouse`: `pg_dump -Fc` of the warehouse → `BACKUP_BUCKET`, pruning dumps older
  than `BACKUP_RETENTION_DAYS`. Skipped when no bucket is configured (local dev).
* `clean_airflow_metadata`: `airflow db clean`. Airflow keeps every task instance, XCom and
  log row forever otherwise, and the metadata DB grows without bound.
* `prune_task_logs`: Airflow doesn't delete its own log files either.
* `check_disk`: alerts on Telegram when the data disk passes 80%.
"""

from __future__ import annotations

import os

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task
from eventalpha_common import DEFAULT_ARGS, START_DATE, settings

RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))
LOG_RETENTION_DAYS = 30
DISK_ALERT_PCT = 80


@dag(
    schedule="30 4 * * *",  # 04:30 ET, after the SEC DAGs, before the US open
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["ops"],
    doc_md=__doc__,
)
def maintenance():
    @task
    def backup_warehouse() -> str:
        import subprocess
        import tempfile
        from datetime import UTC, datetime, timedelta

        from airflow.sdk import Connection

        bucket = os.environ.get("BACKUP_BUCKET", "").strip()
        if not bucket:
            return "skipped: BACKUP_BUCKET not set"
        import boto3

        conn = Connection.get("eventalpha_db")
        env = os.environ | {"PGPASSWORD": conn.password or ""}
        key = f"warehouse/{datetime.now(UTC):%Y/%m/%d}/eventalpha-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.dump"
        with tempfile.NamedTemporaryFile(suffix=".dump") as f:
            subprocess.run(
                ["pg_dump", "-Fc", "-Z", "zstd:6", "-h", conn.host, "-p", str(conn.port or 5432),
                 "-U", conn.login, "-d", conn.schema, "-f", f.name],
                env=env, check=True,
            )
            s3 = boto3.client("s3")
            s3.upload_file(f.name, bucket, key)
            size = os.path.getsize(f.name)

        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        stale = [
            {"Key": o["Key"]}
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="warehouse/")
            for o in page.get("Contents", [])
            if o["LastModified"] < cutoff
        ]
        for i in range(0, len(stale), 1000):
            s3.delete_objects(Bucket=bucket, Delete={"Objects": stale[i : i + 1000]})
        return f"s3://{bucket}/{key} ({size / 1e6:.1f} MB), pruned {len(stale)}"

    clean_metadata = BashOperator(
        task_id="clean_airflow_metadata",
        # Airflow 3 blanks the metadata-DB URL inside tasks; hand the CLI the real one.
        bash_command=(
            'AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="$AIRFLOW_METADATA_DB_URL" '
            "airflow db clean --clean-before-timestamp "
            "\"$(date -u -d '-{{ params.days }} days' +%Y-%m-%dT%H:%M:%S+00:00)\" --skip-archive --yes"
        ),
        params={"days": LOG_RETENTION_DAYS},
    )

    prune_logs = BashOperator(
        task_id="prune_task_logs",
        bash_command=(
            "find /opt/airflow/logs -type f -mtime +{{ params.days }} -delete && "
            "find /opt/airflow/logs -mindepth 1 -type d -empty -delete"
        ),
        params={"days": LOG_RETENTION_DAYS},
    )

    @task
    def check_disk() -> float:
        import shutil

        from eventalpha.alerts import send_telegram

        usage = shutil.disk_usage("/opt/airflow/data")
        pct = 100 * usage.used / usage.total
        if pct >= DISK_ALERT_PCT:
            send_telegram(settings(), f"🟠 <b>EventAlpha disk</b> at {pct:.0f}% "
                                      f"({usage.free / 1e9:.1f} GB free)", ops=True)
        return round(pct, 1)

    backup_warehouse() >> clean_metadata >> prune_logs >> check_disk()


maintenance()
