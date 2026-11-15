"""Market data in provider-neutral terms: quotes, daily bars, and the exchange session calendar.

Pipeline code depends only on this module; vendor APIs live in providers/.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Protocol


class MarketDataError(Exception):
    """A provider call failed (after its own retries)."""


@dataclass(frozen=True)
class Quote:
    symbol: str
    last: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    prev_close: Decimal | None
    change_pct: Decimal | None
    volume: int | None
    trade_date: date | None  # date of the last trade, to spot stale quotes on holidays


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None  # None for indexes (SPX, VIX), which have no volume of their own


@dataclass(frozen=True)
class SessionDay:
    """One calendar day of the US equity market, as the provider's exchange calendar has it."""

    day: date
    is_open: bool
    open_time: time | None  # regular session, America/New_York
    close_time: time | None  # 13:00 on early-close days
    description: str

    @property
    def is_early_close(self) -> bool:
        return self.is_open and self.close_time is not None and self.close_time < time(16, 0)


@dataclass(frozen=True)
class EarningsEvent:
    """A company's scheduled earnings release (date only; providers rarely give the time)."""

    ticker: str
    day: date
    description: str
    status: str  # Confirmed | Estimated
    fiscal_year: int | None


class MarketDataProvider(Protocol):
    name: str

    def quotes(self, symbols: list[str]) -> list[Quote]: ...

    def daily_bars(self, symbol: str, start: date, end: date) -> list[DailyBar]: ...

    def session_calendar(self, year: int, month: int) -> list[SessionDay]: ...

    def earnings_events(self, symbols: list[str], start: date, end: date) -> list[EarningsEvent]: ...

    def market_caps(self, symbols: list[str]) -> dict[str, float]:
        """Market capitalisation in $ by symbol; symbols the provider doesn't know are left out."""
        ...
