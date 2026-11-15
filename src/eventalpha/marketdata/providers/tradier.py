"""Tradier brokerage API (https://documentation.tradier.com/brokerage-api).

Quotes and daily history need the brokerage key (TRADIER_BROKER_KEY). The market calendar is
the broker's own session calendar, holidays and 13:00 early closes included.
"""

from __future__ import annotations

import time as _time
from datetime import date, time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from eventalpha.config import Settings
from eventalpha.marketdata.base import DailyBar, EarningsEvent, MarketDataError, Quote, SessionDay

BASE_URL = "https://api.tradier.com/v1"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _as_list(v: Any) -> list[dict]:
    """Tradier collapses a one-element array into an object, and empty results into null."""
    if not v or v == "null":
        return []
    return [v] if isinstance(v, dict) else list(v)


def _hhmm(v: str | None) -> time | None:
    return time.fromisoformat(v) if v else None


class TradierMarketData:
    name = "tradier"

    def __init__(self, api_key: str | None, base_url: str = BASE_URL, timeout: float = 15.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._has_key = bool(api_key)
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout, transport=transport)

    def _get(self, path: str, params: dict[str, Any], need_key: bool = True) -> dict:
        if need_key and not self._has_key:
            raise MarketDataError("TRADIER_BROKER_KEY is not set")
        for attempt in range(1, 5):
            try:
                resp = self._client.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt == 4:
                    raise MarketDataError(f"Tradier {path}: {exc!r}") from exc
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code not in RETRY_STATUSES or attempt == 4:
                    raise MarketDataError(f"Tradier {path}: HTTP {resp.status_code} {resp.text[:200]}")
            _time.sleep(min(2**attempt, 10))
        raise AssertionError("unreachable")

    def quotes(self, symbols: list[str]) -> list[Quote]:
        if not symbols:
            return []
        data = self._get("/markets/quotes", {"symbols": ",".join(symbols)})
        out = []
        for q in _as_list((data.get("quotes") or {}).get("quote")):
            trade_ms = q.get("trade_date")
            out.append(Quote(
                symbol=q.get("symbol", ""),
                last=_dec(q.get("last")),
                bid=_dec(q.get("bid")),
                ask=_dec(q.get("ask")),
                prev_close=_dec(q.get("prevclose")),
                change_pct=_dec(q.get("change_percentage")),
                volume=q.get("volume"),
                trade_date=date.fromtimestamp(trade_ms / 1000) if trade_ms else None,
            ))
        return out

    def daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]:
        data = self._get("/markets/history", {"symbol": symbol, "interval": "daily",
                                              "start": start.isoformat(), "end": end.isoformat()})
        history = data.get("history")
        days = _as_list(history.get("day")) if isinstance(history, dict) else []
        bars = []
        for d in days:
            o, h, lo, c = (_dec(d.get(k)) for k in ("open", "high", "low", "close"))
            if None in (o, h, lo, c):
                continue
            vol = d.get("volume")
            bars.append(DailyBar(symbol, date.fromisoformat(d["date"]), o, h, lo, c, int(vol) if vol else None))
        return sorted(bars, key=lambda b: b.day)

    def session_calendar(self, year: int, month: int) -> list[SessionDay]:
        data = self._get("/markets/calendar", {"year": year, "month": month}, need_key=False)
        days = _as_list(((data.get("calendar") or {}).get("days") or {}).get("day"))
        out = []
        for d in days:
            session = d.get("open") or {}
            out.append(SessionDay(
                day=date.fromisoformat(d["date"]),
                is_open=d.get("status") == "open",
                open_time=_hhmm(session.get("start")),
                close_time=_hhmm(session.get("end")),
                description=d.get("description", ""),
            ))
        return out

    def earnings_events(self, symbols: list[str], start: date, end: date) -> list[EarningsEvent]:
        """Earnings result dates from Tradier's corporate calendar (fundamentals, beta endpoint)."""
        out: list[EarningsEvent] = []
        for i in range(0, len(symbols), 25):
            chunk = symbols[i : i + 25]
            data = self._get_beta("/markets/fundamentals/calendars", {"symbols": ",".join(chunk)})
            for item in _as_list(data):
                ticker = str(item.get("request", "")).upper()
                for result in _as_list(item.get("results")):
                    # A company with a single event comes back as an object, not a one-item list.
                    for e in _as_list((result.get("tables") or {}).get("corporate_calendars")):
                        text = e.get("event") or ""
                        if "earnings result" not in text.lower():
                            continue  # skip calls, AGMs, annual reports
                        day = date.fromisoformat(e["begin_date_time"][:10])
                        if start <= day <= end:
                            out.append(EarningsEvent(ticker, day, text, e.get("event_status") or "",
                                                     e.get("event_fiscal_year")))
        return out

    def _get_beta(self, path: str, params: dict[str, Any]) -> Any:
        # Same host, /beta prefix instead of /v1.
        url = self._client.base_url.copy_with(path="/beta" + path)
        if not self._has_key:
            raise MarketDataError("TRADIER_BROKER_KEY is not set")
        resp = self._client.get(url, params=params)
        if resp.status_code != 200:
            raise MarketDataError(f"Tradier {path}: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def close(self) -> None:
        self._client.close()


def create(settings: Settings) -> TradierMarketData:
    return TradierMarketData(settings.tradier_broker_key)
