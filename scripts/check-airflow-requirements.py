#!/usr/bin/env python3
"""Fail when docker/requirements-airflow.txt and pyproject.toml drift apart.

The Airflow image installs docker/requirements-airflow.txt on top of what the official image
already ships; pyproject.toml is what tests and local tools use. A package added to one and
not the other works in one place and breaks in the other (the image or the tests).

Rules:
  * every runtime dependency in pyproject.toml is in requirements-airflow.txt, unless the
    Airflow image already ships it (SHIPPED_BY_AIRFLOW);
  * every package in requirements-airflow.txt is a pyproject.toml dependency, except
    Airflow providers, which only the image needs.

Usage: scripts/check-airflow-requirements.py   (exit 1 with a list of differences)
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Already in the apache/airflow image; pinned there by Airflow's own constraints.
SHIPPED_BY_AIRFLOW = {"httpx", "pydantic", "pyyaml", "sqlalchemy"}


def name(requirement: str) -> str:
    """'psycopg[binary]>=3.2' → 'psycopg' (PEP 503 normalized)."""
    base = re.split(r"[\s\[<>=!~;]", requirement.strip(), maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", base).lower()


def main() -> int:
    project = {name(r) for r in tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]}
    image = {
        name(line)
        for line in (ROOT / "docker/requirements-airflow.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing_in_image = sorted(project - image - SHIPPED_BY_AIRFLOW)
    missing_in_project = sorted(p for p in image - project if not p.startswith("apache-airflow-providers-"))
    for p in missing_in_image:
        print(f"pyproject.toml depends on {p}, but docker/requirements-airflow.txt doesn't install it")
    for p in missing_in_project:
        print(f"docker/requirements-airflow.txt installs {p}, but it isn't a pyproject.toml dependency")
    if missing_in_image or missing_in_project:
        return 1
    print(f"in sync: {len(project)} runtime dependencies, {len(SHIPPED_BY_AIRFLOW)} shipped by the Airflow image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
