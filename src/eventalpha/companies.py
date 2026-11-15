"""Which listed companies a news item is about, from the company names it mentions.

Press releases cite "(NYSE: LLY)" in the full text, but RSS items carry only a title and a
short summary, so the ticker is often missing ("Lilly to present new data ...",
"Uber Data Breach Investigation ..."). This matches company names instead, precision first:

* **Full names** from SEC's ticker list, suffixes dropped ("ELI LILLY & Co" → "Eli Lilly",
  "Uber Technologies, Inc" → "Uber Technologies"), as whole phrases, any case.
* **Short names** ("Palantir", "Uber" for "Uber Technologies"): only for the largest
  `SINGLE_WORD_MAX_RANK` companies, only capitalised as a name, and never ordinary words,
  exchanges, places or surnames ("Target", "Nasdaq", "Nova", "Williams").
* **Aliases** from `config/company_aliases.yaml` for names that differ from the SEC name
  ("Lilly", "Google").

Each company gets its primary ticker (the first share class SEC lists for the CIK).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SINGLE_WORD_MAX_RANK = 1500  # SEC lists companies largest first
MAX_RANK = 4000  # beyond this, names are too obscure and too generic to trust
MAX_MATCHES = 3

_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "companies",
    "ltd",
    "limited",
    "plc",
    "llc",
    "lp",
    "sa",
    "nv",
    "ag",
    "se",
    "spa",
    "holdings",
    "holding",
    "group",
    "the",
    "de",
    "com",
    "class",
    "a",
    "b",
    "adr",
    "ads",
    "trust",
    "new",
}
# Big-company names that are also everyday words: never matched on their own.
_COMMON = {
    "target",
    "visa",
    "block",
    "gap",
    "match",
    "shell",
    "apple",
    "amazon",
    "oracle",
    "ford",
    "delta",
    "united",
    "american",
    "general",
    "first",
    "global",
    "national",
    "international",
    "energy",
    "health",
    "capital",
    "financial",
    "bank",
    "realty",
    "royalty",
    "southern",
    "public",
    "progressive",
    "state",
    "best",
    "dollar",
    "booking",
    "service",
    "services",
    "cheniere",
    "mobile",
    "union",
    "pacific",
    "power",
    "insight",
    "core",
    "arch",
    "ally",
    "evergy",
    "equity",
    "fair",
    "simply",
    "summit",
    "uniti",
    "ventas",
    "welltower",
    "nuscale",
    "carrier",
    "corning",
    "loews",
    "domino",
    "chewy",
    "toast",
    "snap",
    "dash",
    "twilio",
    "zoom",
    "square",
    # exchanges, places and surnames that are also company names
    "nasdaq",
    "nyse",
    "nova",
    "williams",
    "johnson",
    "morgan",
    "edison",
    "dominion",
    "eaton",
    "jacobs",
    "baker",
    "moody",
    "hess",
    "murphy",
    "reynolds",
    "cooper",
    "fox",
    "news",
    "texas",
    "canadian",
    "pioneer",
    "phillips",
}
# Descriptors dropped to get the short name people write: "Uber Technologies" → "Uber".
_DESCRIPTORS = {
    "technologies",
    "technology",
    "systems",
    "industries",
    "pharmaceuticals",
    "therapeutics",
    "brands",
    "enterprises",
    "platforms",
    "networks",
    "software",
    "semiconductor",
    "semiconductors",
    "solutions",
    "communications",
    "labs",
    "laboratories",
    "biosciences",
}
# Some of these (Apple, Amazon, Oracle) come back through config/company_aliases.yaml.


@dataclass(frozen=True)
class _Pattern:
    regex: re.Pattern[str]
    ticker: str
    rank: int


def normalize_name(name: str) -> str:
    """SEC company name → the name people write: 'ELI LILLY & Co' → 'Eli Lilly'."""
    words = re.sub(r"/[A-Z]{2}/?", " ", name)  # state tags like /DE/
    words = re.sub(r"[^\w&'\-. ]", " ", words).replace(".", " ").split()
    while words and words[-1].lower().strip("&") in _SUFFIXES | {""}:
        words.pop()
    while words and words[0].lower() == "the":
        words.pop(0)
    return " ".join(w if any(c.islower() for c in w) else w.capitalize() for w in words)


def _phrase(name: str, case_sensitive: bool) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(w) for w in name.split())
    return re.compile(rf"(?<![\w&]){body}(?![\w&])", 0 if case_sensitive else re.IGNORECASE)


class CompanyMatcher:
    def __init__(self, patterns: list[_Pattern]):
        self._patterns = sorted(patterns, key=lambda p: p.rank)

    @classmethod
    def build(
        cls, universe: Iterable[Mapping[str, Any]], aliases: Mapping[str, list[str]] | None = None
    ) -> CompanyMatcher:
        """`universe`: rows with ticker, cik, name, size_rank (the ticker_universe table)."""
        primary: dict[str, Mapping[str, Any]] = {}
        for row in universe:
            rank = row.get("size_rank") or 10**9
            if rank > MAX_RANK:
                continue
            if row["cik"] not in primary or rank < (primary[row["cik"]].get("size_rank") or 10**9):
                primary[row["cik"]] = row
        patterns: list[_Pattern] = []
        seen: set[str] = set()
        for row in primary.values():
            rank, name = row.get("size_rank") or 10**9, normalize_name(row["name"])
            words = name.split()
            key = name.lower()
            if not words or key in seen:
                continue
            if len(words) >= 2:
                patterns.append(_Pattern(_phrase(name, False), row["ticker"], rank))
            short = words[0] if len(words) == 1 or (len(words) == 2 and words[1].lower() in _DESCRIPTORS) else None
            if (
                short
                and rank <= SINGLE_WORD_MAX_RANK
                and len(short) >= 4
                and short.lower() not in _COMMON
                and short.lower() not in seen
            ):
                patterns.append(_Pattern(_phrase(short, True), row["ticker"], rank))
                seen.add(short.lower())
            seen.add(key)
        for ticker, names in (aliases or {}).items():
            for alias in names:
                patterns.append(_Pattern(_phrase(alias, True), ticker.upper(), 0))
        return cls(patterns)

    @classmethod
    def from_db(cls, engine, aliases_path: Path | None = None) -> CompanyMatcher:
        from sqlalchemy import select

        from eventalpha.schema import ticker_universe as tu

        with engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(select(tu.c.ticker, tu.c.cik, tu.c.name, tu.c.size_rank))]
        aliases = yaml.safe_load(aliases_path.read_text()) if aliases_path and aliases_path.exists() else {}
        return cls.build(rows, aliases)

    def find(self, text: str) -> list[str]:
        """Tickers of the companies named in `text`, largest company first, at most MAX_MATCHES."""
        out: list[str] = []
        for p in self._patterns:
            if p.ticker not in out and p.regex.search(text):
                out.append(p.ticker)
                if len(out) == MAX_MATCHES:
                    break
        return out


def merge_tickers(cited: list[str], named: list[str]) -> list[str]:
    """Tickers the text cites explicitly come first; name matches fill in after them."""
    return list(dict.fromkeys([*cited, *named]))
