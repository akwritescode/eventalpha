"""13F-HR: quarterly long holdings of institutional managers with >$100M in US equities.

Filed up to 45 days after quarter end, so it's useless as a next-day signal. It's
collected for positioning / crowding visuals. Holdings are keyed by CUSIP (SEC doesn't map
CUSIPs to tickers); `value_usd` is in dollars for reports since 2023 (thousands before).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from eventalpha.sec.index import IndexEntry
from eventalpha.sec.registry import HOLDINGS_FORMS
from eventalpha.sec.submission import Submission

FORMS = HOLDINGS_FORMS


def _t(el, path: str) -> str | None:
    node = el.find(path)
    return node.text.strip() if node is not None and node.text and node.text.strip() else None


def _n(s: str | None) -> Decimal | None:
    try:
        return Decimal(s.replace(",", "")) if s else None
    except InvalidOperation:
        return None


def _period(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_13f(entry: IndexEntry, sub: Submission) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(filing header, holdings rows). Header carries the period and amendment type."""
    primary = sub.first(entry.form_type)
    table = sub.first("INFORMATION TABLE")
    header: dict[str, Any] = {
        "accession": entry.accession,
        "form_type": entry.form_type,
        "filer_cik": entry.cik,
        "filer_name": entry.company,
        "period_of_report": _period(sub.period_of_report),
        "amendment_type": None,
        "table_entry_total": None,
        "table_value_total": None,
    }
    if primary is not None and primary.is_xml:
        root = primary.xml_root()
        header["period_of_report"] = _period(_t(root, ".//periodOfReport")) or header["period_of_report"]
        header["amendment_type"] = _t(root, ".//amendmentType")  # RESTATEMENT | NEW HOLDINGS
        header["table_entry_total"] = _n(_t(root, ".//tableEntryTotal"))
        header["table_value_total"] = _n(_t(root, ".//tableValueTotal"))
    if table is None or not table.is_xml:
        return header, []

    rows = []
    for i, info in enumerate(table.xml_root().iter("infoTable")):
        rows.append(
            {
                "accession": entry.accession,
                "row_no": i,
                "cusip": (_t(info, "cusip") or "").upper(),
                "issuer_name": _t(info, "nameOfIssuer"),
                "title_of_class": _t(info, "titleOfClass"),
                "value_usd": _n(_t(info, "value")),
                "shares": _n(_t(info, "shrsOrPrnAmt/sshPrnamt")),
                "share_type": _t(info, "shrsOrPrnAmt/sshPrnamtType"),
                "put_call": _t(info, "putCall"),
                "investment_discretion": _t(info, "investmentDiscretion"),
                "voting_sole": _n(_t(info, "votingAuthority/Sole")),
                "voting_shared": _n(_t(info, "votingAuthority/Shared")),
                "voting_none": _n(_t(info, "votingAuthority/None")),
            }
        )
    return header, rows
