"""EDGAR daily form index: every filing accepted on one day, in one small file."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from eventalpha.sec.client import RateLimitedClient

log = logging.getLogger(__name__)

SEC_ARCHIVES = "https://www.sec.gov/Archives"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


@dataclass(frozen=True)
class IndexEntry:
    form_type: str
    company: str
    cik: str
    date_filed: date
    path: str  # edgar/data/<cik>/<accession>.txt

    @property
    def accession(self) -> str:
        return self.path.rsplit("/", 1)[-1].removesuffix(".txt")

    @property
    def submission_url(self) -> str:
        return f"{SEC_ARCHIVES}/{self.path}"

    @property
    def filing_index_url(self) -> str:
        folder = self.accession.replace("-", "")
        return f"{SEC_ARCHIVES}/edgar/data/{self.cik}/{folder}/{self.accession}-index.htm"

    def to_dict(self) -> dict[str, str]:
        return {
            "form_type": self.form_type,
            "company": self.company,
            "cik": self.cik,
            "date_filed": self.date_filed.isoformat(),
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> IndexEntry:
        return cls(
            form_type=d["form_type"],
            company=d["company"],
            cik=d["cik"],
            date_filed=date.fromisoformat(d["date_filed"]),
            path=d["path"],
        )


def daily_index_url(d: date) -> str:
    quarter = (d.month - 1) // 3 + 1
    return f"{SEC_ARCHIVES}/edgar/daily-index/{d.year}/QTR{quarter}/form.{d:%Y%m%d}.idx"


def parse_daily_index(text: str) -> list[IndexEntry]:
    """Fixed-width file: form type (17 chars), company, CIK, YYYYMMDD, path."""
    entries: list[IndexEntry] = []
    body = text.split("-" * 20, 1)[-1]  # skip the header block above the dashed rule
    for line in body.splitlines():
        if len(line) < 20 or not line.strip():
            continue
        form_type = line[:17].strip()
        parts = line[17:].rsplit(None, 3)
        if len(parts) != 4 or not parts[1].isdigit():
            continue
        company, cik, filed, path = parts
        try:
            date_filed = datetime.strptime(filed, "%Y%m%d").date()
        except ValueError:  # one malformed line must not cost the rest of the day's index
            log.warning("skipping daily index line with a bad date: %r", line[:120])
            continue
        entries.append(
            IndexEntry(
                form_type=form_type,
                company=company.strip(),
                cik=cik,
                date_filed=date_filed,
                path=path,
            )
        )
    return entries


def fetch_daily_index(client: RateLimitedClient, d: date) -> list[IndexEntry] | None:
    """None when SEC hasn't published the index (yet, or ever: weekends and holidays)."""
    resp = client.get(daily_index_url(d))
    if resp.status_code in (403, 404):
        return None
    resp.raise_for_status()
    return parse_daily_index(resp.text)


def select_filings(
    entries: Iterable[IndexEntry], forms: frozenset[str], universe_ciks: set[str] | None
) -> list[IndexEntry]:
    """Filings of the given forms, one per accession.

    The index lists a filing once per party (issuer and filer for 13D and Form 4,
    co-registrants for 8-K). Prefer the line whose CIK is in the universe, so the entry
    carries the listed company's CIK. `universe_ciks=None` keeps every filer (13F).
    """
    chosen: dict[str, IndexEntry] = {}
    for e in entries:
        if e.form_type not in forms:
            continue
        in_universe = universe_ciks is None or e.cik in universe_ciks
        if not in_universe:
            continue
        chosen.setdefault(e.accession, e)
    return list(chosen.values())


def fetch_company_tickers(client: RateLimitedClient) -> list[dict[str, Any]]:
    resp = client.get(COMPANY_TICKERS_URL)
    resp.raise_for_status()
    # SEC lists companies largest first (by market value); keep that order as size_rank.
    data = resp.json()
    return [
        {"ticker": r["ticker"].upper(), "cik": str(r["cik_str"]), "name": r["title"], "size_rank": int(k) + 1}
        for k, r in sorted(data.items(), key=lambda kv: int(kv[0]))
    ]
