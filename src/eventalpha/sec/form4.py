"""Form 4: insider transactions (officers, directors, 10% owners), filed within 2 business days.

Structured XML, so no NLP: one row per transaction line. The useful signal is usually
open-market purchases (code P) by officers, especially several insiders at once.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from eventalpha.sec.index import IndexEntry
from eventalpha.sec.registry import INSIDER_FORMS
from eventalpha.sec.submission import Submission

FORMS = INSIDER_FORMS

# https://www.sec.gov/edgar/searchedgar/ownershipformcodes.html (most common)
TRANSACTION_CODES = {
    "P": "open market purchase",
    "S": "open market sale",
    "A": "grant or award",
    "M": "option exercise",
    "F": "tax withholding",
    "G": "gift",
    "D": "disposition to issuer",
    "C": "conversion",
    "X": "option exercise (in the money)",
}


def _val(el, path: str) -> str | None:
    """Form 4 wraps most values as <field><value>..</value></field>; footnotes may replace them."""
    node = el.find(f"{path}/value")
    if node is None:
        node = el.find(path)
    return node.text.strip() if node is not None and node.text and node.text.strip() else None


def _num(s: str | None) -> Decimal | None:
    try:
        return Decimal(s) if s is not None else None
    except InvalidOperation:
        return None


def _bool(s: str | None) -> bool:
    return (s or "").strip().lower() in ("1", "true")


def parse_form4(entry: IndexEntry, sub: Submission) -> list[dict[str, Any]]:
    doc = sub.first(entry.form_type)
    if doc is None or not doc.is_xml:
        return []
    root = doc.xml_root()
    issuer_cik = (_val(root, "issuer/issuerCik") or "").lstrip("0")
    symbol = (_val(root, "issuer/issuerTradingSymbol") or "").upper()
    owners = root.findall("reportingOwner")
    first = owners[0] if owners else None
    rel = first.find("reportingOwnerRelationship") if first is not None else None

    base = {
        "accession": entry.accession,
        "form_type": entry.form_type,
        "issuer_cik": issuer_cik,
        "ticker": symbol if symbol not in ("", "NONE", "N/A") else None,
        "issuer_name": _val(root, "issuer/issuerName"),
        "owner_cik": (_val(first, "reportingOwnerId/rptOwnerCik") or "").lstrip("0") if first is not None else None,
        "owner_name": _val(first, "reportingOwnerId/rptOwnerName") if first is not None else None,
        "owner_count": len(owners),
        "is_director": _bool(_val(rel, "isDirector")) if rel is not None else False,
        "is_officer": _bool(_val(rel, "isOfficer")) if rel is not None else False,
        "is_ten_percent_owner": _bool(_val(rel, "isTenPercentOwner")) if rel is not None else False,
        "officer_title": _val(rel, "officerTitle") if rel is not None else None,
        "filed_at": sub.accepted_at,
    }
    rows = []
    for table, is_derivative in (("nonDerivativeTable", False), ("derivativeTable", True)):
        tag = "derivativeTransaction" if is_derivative else "nonDerivativeTransaction"
        for tx in root.findall(f"{table}/{tag}"):
            tx_date = _val(tx, "transactionDate")
            rows.append(
                base
                | {
                    "row_no": len(rows),
                    "is_derivative": is_derivative,
                    "security_title": _val(tx, "securityTitle"),
                    "transaction_date": date.fromisoformat(tx_date[:10]) if tx_date else None,
                    "transaction_code": _val(tx, "transactionCoding/transactionCode"),
                    "shares": _num(_val(tx, "transactionAmounts/transactionShares")),
                    "price": _num(_val(tx, "transactionAmounts/transactionPricePerShare")),
                    "acquired_disposed": _val(tx, "transactionAmounts/transactionAcquiredDisposedCode"),
                    "shares_owned_after": _num(
                        _val(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction")
                    ),
                    "ownership": _val(tx, "ownershipNature/directOrIndirectOwnership"),
                }
            )
    return rows
