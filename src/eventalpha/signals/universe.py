from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Company:
    name: str
    cik: str
    tickers: tuple[str, ...]
    weight: float  # approximate % of the S&P 500


@dataclass(frozen=True)
class Universe:
    as_of: str
    companies: tuple[Company, ...]
    context_symbols: dict[str, str]

    def by_cik(self) -> dict[str, Company]:
        return {c.cik: c for c in self.companies}

    def by_ticker(self) -> dict[str, Company]:
        return {t: c for c in self.companies for t in c.tickers}


def tradier_symbol(sec_ticker: str) -> str:
    """SEC spells share classes with a hyphen (BRK-B); Tradier uses a slash (BRK/B)."""
    return sec_ticker.replace("-", "/").replace(".", "/")


def sec_ticker(tradier: str) -> str:
    return tradier.replace("/", "-").replace(".", "-")


def load_universe(path: Path) -> Universe:
    data = yaml.safe_load(path.read_text())
    companies = tuple(
        Company(c["name"], str(c["cik"]), tuple(c["tickers"]), float(c["weight"])) for c in data["companies"]
    )
    return Universe(str(data["as_of"]), companies, dict(data.get("context_symbols", {})))
