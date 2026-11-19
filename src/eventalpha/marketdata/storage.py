"""Daily UTC partitions for minute candles, with verified S3 export before reclamation."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import tempfile
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import insert

from eventalpha.schema import price_bars_minute

PREFIX = "minute_bars"
RETENTION_DAYS = 14


def partition_name(day: date) -> str:
    return f"price_bars_minute_p{day:%Y%m%d}"


def ensure_partitions(engine: Engine, start: date, end: date) -> None:
    """Create the collector's range before any writers start."""
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text("SELECT pg_advisory_xact_lock(58421901)"))
        day = start
        while day <= end:
            name = partition_name(day)
            if conn.scalar(text("SELECT to_regclass(:name)"), {"name": name}):
                day += timedelta(days=1)
                continue
            # Move overlapping default rows atomically before attaching the dated table.
            conn.execute(text("LOCK TABLE price_bars_minute IN ACCESS EXCLUSIVE MODE"))
            conn.execute(text(f"CREATE TABLE {name} (LIKE price_bars_minute INCLUDING ALL)"))
            conn.execute(
                text(
                    f"WITH moved AS (DELETE FROM price_bars_minute_default "
                    "WHERE started_at >= :start AND started_at < :end RETURNING *) "
                    f"INSERT INTO {name} SELECT * FROM moved"
                ),
                {
                    "start": datetime.combine(day, datetime.min.time(), UTC),
                    "end": datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC),
                },
            )
            conn.execute(
                text(
                    f"ALTER TABLE price_bars_minute ATTACH PARTITION {name} "
                    f"FOR VALUES FROM ('{day.isoformat()} 00:00:00+00') "
                    f"TO ('{(day + timedelta(days=1)).isoformat()} 00:00:00+00')"
                )
            )
            day += timedelta(days=1)


def store_bars(engine: Engine, rows: list[dict]) -> int:
    """Keep the first observed value and time. Bound SQL parameters during the initial backfill."""
    total = 0
    with engine.begin() as conn:
        for offset in range(0, len(rows), 2000):
            stmt = insert(price_bars_minute).values(rows[offset : offset + 2000]).on_conflict_do_nothing()
            total += conn.execute(stmt).rowcount
    return total


def _digest(file: Any) -> str:
    file.seek(0)
    digest = hashlib.sha256()
    for block in iter(lambda: file.read(1024 * 1024), b""):
        digest.update(block)
    file.seek(0)
    return digest.hexdigest()


def offload_minutes(engine: Engine, s3: Any, bucket: str, now: datetime, *, prefix: str = PREFIX) -> dict:
    """Export and reclaim only complete UTC days older than fourteen full days.

    Upload outside database locks, then compare the snapshot again before DROP.
    Failed verification leaves every Postgres row available for retry.
    """
    prefix = prefix.strip("/")
    if not prefix:
        raise ValueError("An archive prefix is required")
    if not bucket.strip() or now.utcoffset() is None:
        raise ValueError("An archive bucket and offset-aware clock are required")
    cutoff = now.astimezone(UTC).date() - timedelta(days=RETENTION_DAYS)
    with engine.connect() as conn:
        default_days = (
            conn.execute(text("SELECT DISTINCT (started_at AT TIME ZONE 'UTC')::date FROM price_bars_minute_default"))
            .scalars()
            .all()
        )
    for day in default_days:
        ensure_partitions(engine, day, day)
    with engine.connect() as conn:
        partitions = (
            conn.execute(
                text("""
            SELECT child.relname FROM pg_inherits
            JOIN pg_class parent ON parent.oid = inhparent
            JOIN pg_class child ON child.oid = inhrelid
            JOIN pg_namespace ns ON ns.oid = parent.relnamespace
            WHERE parent.relname = 'price_bars_minute' AND ns.nspname = current_schema()
            ORDER BY child.relname
        """)
            )
            .scalars()
            .all()
        )
    archived = []
    for name in partitions:
        if not re.fullmatch(r"price_bars_minute_p[0-9]{8}", name):
            continue
        day = datetime.strptime(name[-8:], "%Y%m%d").date()
        if day >= cutoff:
            continue
        with tempfile.TemporaryFile() as payload, tempfile.TemporaryFile() as verified:
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(text(f"LOCK TABLE {name} IN SHARE MODE"))
                snapshot = conn.execute(text(f"SELECT count(*), max(first_seen_at) FROM {name}")).one()
                count = 0
                with gzip.GzipFile(fileobj=payload, mode="wb", mtime=0) as compressed:
                    rows = conn.execute(
                        text(f"SELECT * FROM {name} ORDER BY symbol, started_at").execution_options(stream_results=True)
                    )
                    for row in rows.mappings():
                        compressed.write((json.dumps(dict(row), default=str, sort_keys=True) + "\n").encode())
                        count += 1
            checksum = _digest(payload)
            key = f"{prefix}/dt={day.isoformat()}/part-{checksum}.jsonl.gz"
            s3.upload_fileobj(payload, bucket, key, ExtraArgs={"ContentType": "application/gzip"})
            s3.download_fileobj(bucket, key, verified)
            if _digest(verified) != checksum:
                raise ValueError(f"Archive checksum mismatch for {day}")
            with gzip.GzipFile(fileobj=verified, mode="rb") as compressed:
                checked = 0
                for line in compressed:
                    record = json.loads(line)
                    if datetime.fromisoformat(record["started_at"]).astimezone(UTC).date() != day:
                        raise ValueError(f"Archive date mismatch for {day}")
                    checked += 1
            if checked != count:
                raise ValueError(f"Archive row count mismatch for {day}")
            manifest = {
                "schema_version": 1,
                "table": "price_bars_minute",
                "dt": day.isoformat(),
                "rows": count,
                "sha256": checksum,
                "key": key,
                "columns": list(price_bars_minute.columns.keys()),
                "written_at": now.isoformat(),
            }
            manifest_key = f"{prefix}/dt={day.isoformat()}/_manifest.json"
            s3.put_object(
                Bucket=bucket, Key=manifest_key, Body=json.dumps(manifest).encode(), ContentType="application/json"
            )
            response = s3.get_object(Bucket=bucket, Key=manifest_key)
            try:
                saved = json.loads(response["Body"].read())
            finally:
                response["Body"].close()
            if saved != manifest:
                raise ValueError(f"Archive manifest mismatch for {day}")
            # Candle writes are insert-only. Check their count and newest observation
            # in SQL, without re-encoding a day's payload while the parent is locked.
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(text("SELECT pg_advisory_xact_lock(58421901)"))
                conn.execute(text("LOCK TABLE ONLY price_bars_minute IN ACCESS EXCLUSIVE MODE"))
                conn.execute(text(f"LOCK TABLE {name} IN ACCESS EXCLUSIVE MODE"))
                current = conn.execute(text(f"SELECT count(*), max(first_seen_at) FROM {name}")).one()
                if current != snapshot:
                    raise ValueError(f"Partition changed during archive for {day}; retained for retry")
                conn.execute(text(f"DROP TABLE {name}"))
                archived.append({"day": day.isoformat(), "rows": count, "key": key})
    return {"bucket": bucket, "prefix": prefix, "archived": archived}
