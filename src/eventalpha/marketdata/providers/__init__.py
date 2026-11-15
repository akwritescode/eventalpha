"""Market data providers. Each module exposes `create(settings) -> MarketDataProvider`."""

from __future__ import annotations

import importlib

from eventalpha.config import Settings
from eventalpha.marketdata.base import MarketDataProvider

PROVIDERS: dict[str, str] = {
    "tradier": "eventalpha.marketdata.providers.tradier",
}


def create_market_data(settings: Settings) -> MarketDataProvider:
    try:
        module = importlib.import_module(PROVIDERS[settings.market_data_provider])
    except KeyError:
        raise ValueError(
            f"unknown market data provider {settings.market_data_provider!r}; known: {sorted(PROVIDERS)}"
        ) from None
    return module.create(settings)
