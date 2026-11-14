"""Raw landing zone: what each source returned, before any database write.

Layout: <source>/dt=<YYYY-MM-DD>/<run_id>.jsonl, under a local directory (dev) or an S3 /
Lightsail bucket (production). Keeping raw data lets you re-parse or re-model without
re-fetching, which matters for sources that can't be re-queried (RSS keeps only recent items).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.=-]+", "_", s)


def landing_key(source: str, dt: date, run_id: str) -> str:
    return f"{_safe(source)}/dt={dt:%Y-%m-%d}/{_safe(run_id)}.jsonl"


def write_jsonl(
    root: Path,
    source: str,
    dt: date,
    run_id: str,
    records: Iterable[dict[str, Any]],
    bucket: str | None = None,
) -> str:
    """Write records as JSON lines; returns the local path or s3:// URI written."""
    body = "".join(json.dumps(rec, default=str) + "\n" for rec in records)
    key = landing_key(source, dt, run_id)
    if bucket:
        import boto3

        # put_object replaces the whole object, so a retried task never leaves a partial file.
        boto3.client("s3").put_object(Bucket=bucket, Key=f"raw/{key}", Body=body.encode(),
                                      ContentType="application/x-ndjson")
        return f"s3://{bucket}/raw/{key}"
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text(body)
    tmp.replace(path)  # atomic rename: no half-written file survives a crash
    return str(path)
