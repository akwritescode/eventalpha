"""BLS (https://www.bls.gov/developers/). For what FRED lags on or doesn't carry.

* Time series API v2: works without a key (low daily limit); BLS_API_KEY raises the limit.
* Release calendar: BLS publishes its schedule as an iCalendar file with exact ET release
  times (CPI, PPI, Employment Situation, JOLTS, ... mostly 08:30 ET).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx

API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
CALENDAR_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
NY = ZoneInfo("America/New_York")

# Series the signals use. id -> description.
SERIES: dict[str, str] = {
    "CUSR0000SA0": "CPI-U, all items (SA index): month-over-month surprise vs nowcast",
    "CUSR0000SA0L1E": "CPI-U, core (SA index): month-over-month surprise vs nowcast",
    "CUUR0000SA0": "CPI-U, all items (NSA index)",
    "CUUR0000SA0L1E": "CPI-U, core: all items less food and energy (NSA index)",
    "CES0000000001": "Total nonfarm employment (thousands, SA)",
    "LNS14000000": "Unemployment rate (SA, %)",
    "WPUFD4": "PPI, final demand (index)",
}


class BlsError(Exception):
    pass


@dataclass(frozen=True)
class BlsObservation:
    series_id: str
    year: int
    period: str  # "M10" = October; "M13" = annual average
    value: Decimal | None
    preliminary: bool  # BLS footnote "P": revised in later releases


@dataclass(frozen=True)
class ScheduledRelease:
    title: str
    at: datetime  # America/New_York


class BlsClient:
    def __init__(self, api_key: str | None, user_agent: str, timeout: float = 30.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._key = api_key
        self._client = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": user_agent})

    def series(self, series_ids: list[str], start_year: int, end_year: int) -> list[BlsObservation]:
        body: dict = {"seriesid": series_ids, "startyear": str(start_year), "endyear": str(end_year)}
        if self._key:
            body["registrationkey"] = self._key
        resp = self._client.post(API_URL, json=body)
        data = resp.json() if resp.status_code == 200 else {}
        if data.get("status") != "REQUEST_SUCCEEDED":
            raise BlsError(f"BLS API: HTTP {resp.status_code} {data.get('message') or resp.text[:200]}")
        out = []
        for s in data["Results"]["series"]:
            for d in s.get("data", []):
                try:
                    value = Decimal(d["value"])
                except (InvalidOperation, KeyError):
                    value = None
                prelim = any((f or {}).get("code") == "P" for f in d.get("footnotes", []))
                out.append(BlsObservation(s["seriesID"], int(d["year"]), d["period"], value, prelim))
        return out

    def release_calendar(self) -> list[ScheduledRelease]:
        resp = self._client.get(CALENDAR_URL)
        if resp.status_code != 200:
            raise BlsError(f"BLS calendar: HTTP {resp.status_code}")
        return parse_ics(resp.text)

    def close(self) -> None:
        self._client.close()


_EVENT = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.S)


def parse_ics(text: str) -> list[ScheduledRelease]:
    """Minimal iCalendar reader for BLS's file: SUMMARY + DTSTART;TZID=US-Eastern:YYYYMMDDTHHMMSS."""
    text = re.sub(r"\r?\n[ \t]", "", text)  # unfold continuation lines
    out = []
    for block in _EVENT.findall(text):
        summary = re.search(r"^SUMMARY:(.*)$", block, re.M)
        start = re.search(r"^DTSTART[^:]*:(\d{8}T\d{6})", block, re.M)
        if summary and start:
            at = datetime.strptime(start.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=NY)
            out.append(ScheduledRelease(summary.group(1).strip().replace("\\,", ","), at))
    return sorted(out, key=lambda r: r.at)
