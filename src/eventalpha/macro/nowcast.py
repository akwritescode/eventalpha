"""Cleveland Fed inflation nowcasts (https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting).

The page's charts load three JSON files (month-over-month, quarter annualized, year-over-year).
Each file is a list of charts, one per target period, whose datasets hold a value per daily
nowcast vintage for CPI, core CPI, PCE and core PCE, plus the actual once it's released.
Updated each business day around 10:00 ET.

Source: Federal Reserve Bank of Cleveland, Inflation Nowcasting (doi:10.26509/frbc-inflationnowcast).
Reused for non-commercial research with attribution, per the Bank's terms of use.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

BASE = "https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting"
FILES = {"mom": "nowcast_month.json", "qoq": "nowcast_quarter.json", "yoy": "nowcast_year.json"}
MEASURES = {
    "CPI Inflation": "cpi",
    "Core CPI Inflation": "core_cpi",
    "PCE Inflation": "pce",
    "Core PCE Inflation": "core_pce",
}


def _dec(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except InvalidOperation:
        return None


def _target_start(period: str) -> date:
    """'2026-11' -> 2026-11-01, '2026:Q4' -> 2026-10-01."""
    if ":Q" in period:
        year, q = period.split(":Q")
        return date(int(year), 3 * (int(q) - 1) + 1, 1)
    year, month = period.split("-")
    return date(int(year), int(month), 1)


def normalize_period(period: str) -> str:
    """The source writes months unpadded ("2026-9"), which sorts after "2026-11" as text.
    Zero-pad so periods sort correctly and match "%Y-%m" lookups."""
    if ":Q" in period:
        return period
    year, month = period.split("-")
    return f"{int(year)}-{int(month):02d}"


def vintage_date(label: str, period: str) -> date:
    """Vintage labels are 'MM/DD' without a year. Nowcasting for a period starts in its first
    month and runs until the release, which can be in the following year (Dec -> Jan)."""
    month, day = (int(x) for x in label.split("/"))
    start = _target_start(period)
    year = start.year if month >= start.month else start.year + 1
    return date(year, month, day)


def parse_charts(horizon: str, charts: list[dict], last_n_periods: int = 3) -> list[dict[str, Any]]:
    """Rows for the most recent target periods (older periods are final and never change)."""
    rows: list[dict[str, Any]] = []
    # Sort by target period rather than trusting the file's chart order ("YYYY-MM" and
    # "YYYY:Qn" both sort chronologically as text).
    charts = sorted(charts, key=lambda c: normalize_period(c["chart"]["subcaption"]))
    for chart in charts[-last_n_periods:]:
        period = normalize_period(chart["chart"]["subcaption"])  # "2026-11" or "2026:Q4"
        labels = [c["label"] for c in chart["categories"][0]["category"]]
        by_name = {d["seriesname"]: [_dec(x.get("value")) for x in d.get("data", [])] for d in chart["dataset"]}
        for name, measure in MEASURES.items():
            values = by_name.get(name, [])
            actual = next((v for v in reversed(by_name.get(f"Actual {name}", [])) if v is not None), None)
            for label, value in zip(labels, values, strict=False):
                if value is None or not label[:1].isdigit():  # skip "CPI Oct"-style marker columns
                    continue
                rows.append(
                    {
                        "horizon": horizon,
                        "target_period": period,
                        "measure": measure,
                        "vintage": vintage_date(label, period),
                        "value": value,
                        "actual": actual,
                    }
                )
    return rows


def fetch_nowcasts(user_agent: str, timeout: float = 60.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with httpx.Client(headers={"User-Agent": user_agent}, timeout=timeout) as client:
        for horizon, name in FILES.items():
            resp = client.get(f"{BASE}/{name}")
            resp.raise_for_status()
            rows.extend(parse_charts(horizon, resp.json()))
    return rows
