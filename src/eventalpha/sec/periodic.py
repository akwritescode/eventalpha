"""10-K / 10-Q: narrative sections plus structured financials from XBRL.

* Sections: Risk Factors and MD&A, pulled out of the main document by their item headings.
  Stored whole (not sent to Jev yet). The research use is comparing a company's language
  with its previous filing: changes in 10-K text predict returns ("Lazy Prices",
  Cohen, Malloy & Nguyen 2020).
* Facts: a short list of headline XBRL concepts from SEC's companyfacts API, keeping only the
  values reported in *this* filing (matching accession number).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from eventalpha.sec.client import RateLimitedClient
from eventalpha.sec.index import IndexEntry
from eventalpha.sec.registry import PERIODIC_FORMS
from eventalpha.sec.submission import Submission

FORMS = PERIODIC_FORMS
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
MAX_SECTION_CHARS = 400_000
MIN_SECTION_CHARS = 200  # shorter is a table-of-contents line or "see Annual Report"

# (section, item code, heading keyword) per form family.
SECTIONS = {
    "10-K": [("risk_factors", "1A", "risk"), ("mdna", "7", "management")],
    "10-Q": [("risk_factors", "1A", "risk"), ("mdna", "2", "management")],
}

# Headings start a line; cross-references ("see Item 1A, Risk Factors") sit mid-sentence.
_HEADING = re.compile(
    r"^[ \t]*(?:part\s+[iv]+\W{0,3}\s*)?item\s*(\d{1,2}[A-C]?)\s*[.:\-–—]?\s*([A-Za-z][^\n]{0,80})",
    re.I | re.M,
)

CONCEPTS: dict[str, tuple[str, ...]] = {
    "us-gaap": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "NetIncomeLoss",
        "OperatingIncomeLoss",
        "EarningsPerShareBasic",
        "EarningsPerShareDiluted",
        "CashAndCashEquivalentsAtCarryingValue",
        "Assets",
        "Liabilities",
        "StockholdersEquity",
        "LongTermDebt",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsForRepurchaseOfCommonStock",
    ),
    "dei": ("EntityCommonStockSharesOutstanding",),
}


def extract_sections(form_type: str, text: str) -> dict[str, str]:
    """Pick, for each target item, the heading occurrence followed by the longest span.

    Filings list each heading at least twice (table of contents, then the section); the
    real section is the occurrence that runs longest before the next heading line.
    """
    family = form_type.split("/")[0]
    headings = [(m.start(), m.group(1).upper(), m.group(2).lower()) for m in _HEADING.finditer(text)]
    out: dict[str, str] = {}
    for section, code, keyword in SECTIONS.get(family, []):
        best = ""
        for i, (start, c, title) in enumerate(headings):
            if c != code or keyword not in title[:40]:
                continue
            end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
            span = text[start:end].strip()
            if len(span) > len(best):
                best = span
        if len(best) >= MIN_SECTION_CHARS:
            out[section] = best[:MAX_SECTION_CHARS]
    return out


def section_rows(entry: IndexEntry, sub: Submission) -> list[dict[str, Any]]:
    main = sub.first(entry.form_type)
    if main is None:
        return []
    period = date.fromisoformat(f"{p[:4]}-{p[4:6]}-{p[6:]}") if (p := sub.period_of_report) else None
    return [
        {
            "accession": entry.accession,
            "section": name,
            "cik": entry.cik,
            "form_type": entry.form_type,
            "period_of_report": period,
            "text": body,
            "chars": len(body),
        }
        for name, body in extract_sections(entry.form_type, main.text).items()
    ]


def fetch_fact_rows(client: RateLimitedClient, entry: IndexEntry) -> list[dict[str, Any]]:
    resp = client.get(COMPANY_FACTS_URL.format(cik=entry.cik))
    if resp.status_code == 404:  # no XBRL on file (e.g. some foreign or tiny filers)
        return []
    resp.raise_for_status()
    facts = resp.json().get("facts", {})
    rows: dict[tuple, dict[str, Any]] = {}
    for taxonomy, names in CONCEPTS.items():
        for name in names:
            for unit, values in facts.get(taxonomy, {}).get(name, {}).get("units", {}).items():
                for v in values:
                    if v.get("accn") != entry.accession:
                        continue
                    row = {
                        "accession": entry.accession,
                        "cik": entry.cik,
                        "concept": f"{taxonomy}:{name}",
                        "unit": unit,
                        "period_start": date.fromisoformat(v["start"]) if v.get("start") else None,
                        "period_end": date.fromisoformat(v["end"]),
                        "value": Decimal(str(v["val"])),
                        "fiscal_year": v.get("fy"),
                        "fiscal_period": v.get("fp"),
                        "form_type": v.get("form"),
                        "frame": v.get("frame"),
                    }
                    rows[(row["concept"], unit, row["period_start"], row["period_end"])] = row
    return list(rows.values())
