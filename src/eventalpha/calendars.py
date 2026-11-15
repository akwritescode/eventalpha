"""Scheduled market-moving events: economic releases (BLS + FRED) and company earnings dates."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from eventalpha.macro.bls import ScheduledRelease
from eventalpha.macro.fred import ReleaseDate
from eventalpha.marketdata.base import EarningsEvent

# BLS release titles that move the index, by importance. Matched by prefix.
BLS_IMPORTANCE: dict[str, str] = {
    "Employment Situation": "high",
    "Consumer Price Index": "high",
    "Producer Price Index": "medium",
    "Job Openings and Labor Turnover Survey": "medium",
    "Employment Cost Index": "medium",
    "U.S. Import and Export Price Indexes": "medium",
    "Real Earnings": "medium",
    "Productivity and Costs": "medium",
}

# FRED release names (exact match) for releases BLS doesn't publish. Dates only. FOMC
# decisions come from the Fed's own calendar (fomc_event_rows): FRED lists its FOMC release daily.
FRED_IMPORTANCE: dict[str, str] = {
    "Gross Domestic Product": "high",
    "Personal Income and Outlays": "high",  # PCE inflation
    "Advance Monthly Sales for Retail and Food Services": "high",
    "Unemployment Insurance Weekly Claims Report": "medium",
    "Industrial Production and Capacity Utilization": "medium",
    "New Residential Construction": "medium",
    "Surveys of Consumers": "medium",  # University of Michigan sentiment and inflation expectations
    "Manufacturers' Shipments, Inventories, and Orders": "medium",
    "ADP National Employment Report": "medium",
}
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}


def _key(*parts: str) -> str:
    return re.sub(r"\s+", " ", "|".join(parts))[:200]


def bls_event_rows(releases: list[ScheduledRelease], start: date, end: date) -> list[dict[str, Any]]:
    rows = []
    for r in releases:
        importance = next((v for k, v in BLS_IMPORTANCE.items() if r.title.startswith(k)), None)
        if importance and start <= r.at.date() <= end:
            rows.append(
                {
                    "source": "bls",
                    "event_key": _key(r.title, r.at.isoformat()),
                    "title": r.title,
                    "event_date": r.at.date(),
                    "scheduled_at": r.at,
                    "importance": importance,
                }
            )
    return rows


def fred_event_rows(releases: list[ReleaseDate]) -> list[dict[str, Any]]:
    rows = []
    for r in releases:
        importance = FRED_IMPORTANCE.get(r.name)
        if importance:
            rows.append(
                {
                    "source": "fred",
                    "event_key": _key(str(r.release_id), r.day.isoformat()),
                    "title": r.name,
                    "event_date": r.day,
                    "scheduled_at": None,
                    "importance": importance,
                }
            )
    return rows


def _month(name: str) -> int:
    name = name.strip().lower()[:3]
    return next((n for m, n in _MONTHS.items() if m.startswith(name)), 0) if name else 0


def fomc_event_rows(html: str, start: date, end: date) -> list[dict[str, Any]]:
    """Scheduled FOMC decisions from the Fed's calendar page (public domain). The statement is
    released at 14:00 ET on the last day of the meeting; '*' marks meetings with projections."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from bs4 import BeautifulSoup

    rows = []
    for panel in BeautifulSoup(html, "lxml").select("div.panel.panel-default"):
        heading = panel.select_one(".panel-heading")
        year_m = re.search(r"(\d{4}) FOMC Meetings", heading.get_text(" ", strip=True) if heading else "")
        if not year_m:
            continue
        year = int(year_m.group(1))
        for meeting in panel.select(".fomc-meeting"):
            month_el, date_el = meeting.select_one(".fomc-meeting__month"), meeting.select_one(".fomc-meeting__date")
            if not (month_el and date_el):
                continue
            days = re.match(r"(\d+)(?:-(\d+))?(\*)?$", date_el.get_text(strip=True))
            if not days:
                continue  # notation votes and unscheduled meetings
            months = [_month(m) for m in month_el.get_text(strip=True).split("/")]  # "Apr/May"
            last_day = int(days.group(2) or days.group(1))
            month = months[-1] if days.group(2) and int(days.group(2)) < int(days.group(1)) else months[0]
            if not month:
                continue
            at = datetime(year, month, last_day, 14, 0, tzinfo=ZoneInfo("America/New_York"))
            if start <= at.date() <= end:
                title = "FOMC rate decision" + (" + projections" if days.group(3) else "")
                rows.append(
                    {
                        "source": "fed",
                        "event_key": _key(title, at.date().isoformat()),
                        "title": title,
                        "event_date": at.date(),
                        "scheduled_at": at,
                        "importance": "high",
                    }
                )
    return rows


def earnings_rows(events: list[EarningsEvent], source: str) -> list[dict[str, Any]]:
    """One row per (ticker, date). A confirmed date drops estimated ones within a week of it."""
    seen: dict[tuple[str, date], dict[str, Any]] = {}
    for e in events:
        seen[(e.ticker, e.day)] = {
            "ticker": e.ticker,
            "event_date": e.day,
            "description": e.description,
            "status": e.status,
            "fiscal_year": e.fiscal_year,
            "source": source,
        }
    confirmed = {(t, d) for (t, d), r in seen.items() if r["status"] == "Confirmed"}
    return [
        r
        for (t, d), r in seen.items()
        if r["status"] == "Confirmed" or not any(t == ct and abs((d - cd).days) <= 7 for ct, cd in confirmed)
    ]
