"""FRED API (https://fred.stlouisfed.org/docs/api/fred/). Free key: FRED_API_KEY.

Two uses:
* observations: daily/monthly series (yields, oil, VIX, dollar, CPI, payrolls, ...)
* release dates: the schedule of upcoming data releases (CPI, jobs, GDP, retail sales, ...)

Daily market series on FRED are published with about a one-day lag, so they're history and
context; same-day prices come from the market data provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

BASE_URL = "https://api.stlouisfed.org/fred"

# Series the signals use. id -> description. Extend freely; each is one row per observation.
SERIES: dict[str, str] = {
    "DGS2": "2-year Treasury yield (%)",
    "DGS10": "10-year Treasury yield (%)",
    "T10Y2Y": "10y minus 2y Treasury spread (%)",
    "DFF": "Effective federal funds rate (%)",
    "DCOILWTICO": "WTI crude oil, Cushing ($/bbl)",
    "VIXCLS": "CBOE VIX close",
    "DTWEXBGS": "Trade-weighted US dollar index (broad)",
    "BAMLH0A0HYM2": "High-yield OAS (credit stress, %)",
    "CPIAUCSL": "CPI, all items (index, SA)",
    "PAYEMS": "Nonfarm payrolls (thousands, SA)",
    "UNRATE": "Unemployment rate (%)",
}


class FredError(Exception):
    pass


@dataclass(frozen=True)
class Observation:
    series_id: str
    day: date
    value: Decimal | None  # FRED uses "." for missing values


@dataclass(frozen=True)
class ReleaseDate:
    release_id: int
    name: str
    day: date


class FredClient:
    def __init__(self, api_key: str | None, timeout: float = 20.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        if not api_key:
            raise FredError("FRED_API_KEY is not set (free key: https://fredaccount.stlouisfed.org/apikeys)")
        self._key = api_key
        self._client = httpx.Client(base_url=BASE_URL, timeout=timeout, transport=transport)

    def _get(self, path: str, params: dict) -> dict:
        resp = self._client.get(path, params=params | {"api_key": self._key, "file_type": "json"})
        if resp.status_code != 200:
            raise FredError(f"FRED {path}: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def observations(self, series_id: str, start: date, end: date | None = None) -> list[Observation]:
        params = {"series_id": series_id, "observation_start": start.isoformat()}
        if end:
            params["observation_end"] = end.isoformat()
        out = []
        for o in self._get("/series/observations", params).get("observations", []):
            try:
                value = Decimal(o["value"]) if o["value"] not in (".", "") else None
            except InvalidOperation:
                value = None
            out.append(Observation(series_id, date.fromisoformat(o["date"]), value))
        return out

    def release_dates(self, start: date, end: date) -> list[ReleaseDate]:
        data = self._get("/releases/dates", {
            "realtime_start": start.isoformat(), "realtime_end": end.isoformat(),
            "include_release_dates_with_no_data": "true", "limit": 1000, "sort_order": "asc",
        })
        return [ReleaseDate(int(r["release_id"]), r["release_name"], date.fromisoformat(r["date"]))
                for r in data.get("release_dates", [])]

    def close(self) -> None:
        self._client.close()
