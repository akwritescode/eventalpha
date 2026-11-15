"""Text-event filings that become Articles and get classified:
8-K (US current report), 6-K (foreign issuer report), Schedule 13D (activist / >5% stake
with intent), S-1 and 424B4/424B5 (offerings, i.e. dilution)."""

from __future__ import annotations

import re
from datetime import datetime

from eventalpha.models import Article
from eventalpha.sec.index import IndexEntry
from eventalpha.sec.registry import EVENT_FORMS
from eventalpha.sec.submission import EASTERN, Submission

FORMS = EVENT_FORMS

# Header "ITEM INFORMATION" lines carry the item's title; map titles to item codes.
ITEM_CODES: dict[str, str] = {
    "entry into a material definitive agreement": "1.01",
    "termination of a material definitive agreement": "1.02",
    "bankruptcy or receivership": "1.03",
    "mine safety": "1.04",
    "material cybersecurity incidents": "1.05",
    "completion of acquisition or disposition of assets": "2.01",
    "results of operations and financial condition": "2.02",
    "creation of a direct financial obligation": "2.03",
    "triggering events that accelerate or increase": "2.04",
    "costs associated with exit or disposal activities": "2.05",
    "material impairments": "2.06",
    "notice of delisting": "3.01",
    "unregistered sales of equity securities": "3.02",
    "material modification": "3.03",
    "changes in registrant's certifying accountant": "4.01",
    "non-reliance on previously issued financial statements": "4.02",
    "changes in control of registrant": "5.01",
    "departure of directors or certain officers": "5.02",
    "amendments to articles of incorporation or bylaws": "5.03",
    "temporary suspension of trading under registrant's employee benefit plans": "5.04",
    "amendments to the registrant's code of ethics": "5.05",
    "change in shell company status": "5.06",
    "submission of matters to a vote of security holders": "5.07",
    "shareholder director nominations": "5.08",
    "regulation fd disclosure": "7.01",
    "other events": "8.01",
    "financial statements and exhibits": "9.01",
}


def item_codes(titles: list[str]) -> list[str]:
    codes = []
    for title in titles:
        t = title.lower()
        code = next((c for prefix, c in ITEM_CODES.items() if t.startswith(prefix)), None)
        if code:
            codes.append(code)
    return codes


def _generic(description: str, doc_type: str) -> bool:
    d = description.strip().upper().replace("EXHIBIT", "EX").replace(" ", "").replace("-", "")
    return d in ("", doc_type.replace("-", "")) or bool(re.fullmatch(r"EX\d+(\.\d+)?", d))


def _first_line(text: str, max_len: int = 150) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if 12 <= len(line) <= max_len and not line.upper().startswith(("EXHIBIT", "EX-99")):
            return line
    return None


def _published(entry: IndexEntry, sub: Submission) -> datetime:
    return sub.accepted_at or datetime.combine(entry.date_filed, datetime.min.time(), tzinfo=EASTERN)


def to_article(entry: IndexEntry, sub: Submission, cik_map: dict[str, tuple[str, list[str]]]) -> Article | None:
    """None when the filing isn't about a company in the universe (e.g. 13D on a private issuer)."""
    form = entry.form_type
    if form.startswith("SCHEDULE 13D"):
        return _schedule_13d(entry, sub, cik_map)

    _, tickers = cik_map.get(entry.cik, ("", []))
    exhibits = sub.of_prefix("EX-99")
    main = sub.first(form)
    # For 8-K/6-K the press release exhibit is the news; the cover document is boilerplate.
    body_docs = exhibits or ([main] if main else [])
    if form == "8-K":
        items = [t for t in sub.item_titles if not t.lower().startswith("financial statements and exhibits")]
        headline = "; ".join(items) or "Current report"
    elif form == "6-K":
        labels = (d.description for d in exhibits if d.description and not _generic(d.description, d.type))
        headline = next(labels, None)
        # A generic exhibit label ("EXHIBIT 99.1") says nothing; the press release's first line does.
        headline = headline or next((_first_line(d.text) for d in exhibits if _first_line(d.text)), None)
        headline = headline or "Report of foreign private issuer"
    else:  # S-1, 424B4, 424B5: the prospectus cover and summary say what is being sold
        headline = {
            "S-1": "Registration statement (S-1)",
            "424B4": "Final IPO prospectus (424B4)",
            "424B5": "Securities offering prospectus (424B5)",
        }[form]
    return Article(
        source="sec_edgar",
        source_id=entry.accession,
        form_type=form,
        url=entry.filing_index_url,
        title=f"{entry.company} {form}: {headline}",
        summary="; ".join(sub.item_titles) or None,
        body="\n\n".join(d.text for d in body_docs) or None,
        company=entry.company,
        cik=entry.cik,
        tickers=tickers,
        sec_items=item_codes(sub.item_titles) if form == "8-K" else [],
        published_at=_published(entry, sub),
    )


def _text(root, path: str) -> str | None:
    el = root.find(path)
    return el.text.strip() if el is not None and el.text and el.text.strip() else None


def _schedule_13d(entry: IndexEntry, sub: Submission, cik_map: dict[str, tuple[str, list[str]]]) -> Article | None:
    doc = sub.first(entry.form_type)
    if doc is None or not doc.is_xml:
        return None
    root = doc.xml_root()
    issuer_cik = (_text(root, ".//issuerCIK") or "").lstrip("0")
    if issuer_cik not in cik_map:
        return None
    issuer_name, tickers = cik_map[issuer_cik]
    reporters = [el.text.strip() for el in root.iter("reportingPersonName") if el.text]
    pcts = [float(el.text) for el in root.iter("percentOfClass") if el.text and el.text.strip()]
    pct = max(pcts) if pcts else None
    amended = entry.form_type.endswith("/A")
    lead = reporters[0] if reporters else "Investor"
    stake = f"{pct:g}% " if pct is not None else ""
    verb = "amends its" if amended else "discloses a"
    title = f"{lead} {verb} {stake}stake in {issuer_name} (Schedule 13D{'/A' if amended else ''})"

    # Items 3-6 carry the narrative: source of funds, purpose and plans, interest, agreements.
    sections = []
    for tag, label in (
        ("item4", "Purpose of transaction"),
        ("item3", "Source of funds"),
        ("item5", "Interest in securities"),
        ("item6", "Contracts and arrangements"),
    ):
        el = root.find(f".//{tag}")
        if el is not None:
            text = " ".join(t.strip() for t in el.itertext() if t.strip())
            if text:
                sections.append(f"{label}: {text}")
    return Article(
        source="sec_edgar",
        source_id=entry.accession,
        form_type=entry.form_type,
        url=entry.filing_index_url,
        title=title,
        summary=f"Reporting persons: {', '.join(reporters[:5])}" + (f"; {pct:g}% of class" if pct else ""),
        body="\n\n".join(sections) or None,
        company=issuer_name,
        cik=issuer_cik,
        tickers=tickers,
        published_at=_published(entry, sub),
    )
