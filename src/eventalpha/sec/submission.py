"""Complete-submission text files (<accession>.txt): SGML header plus every document.

Only the head of the file is read: streaming stops at the first image, XBRL, or archive
document, which for most filings is 90%+ of the bytes.
"""

from __future__ import annotations

import logging
import re
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from lxml import etree

from eventalpha.sec.client import RateLimitedClient
from eventalpha.sec.index import IndexEntry
from eventalpha.text import html_to_text

log = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")
MAX_FILING_BYTES = 32 * 1024 * 1024  # large 13F information tables run to tens of MB

_STOP_TYPES = re.compile(r"^(GRAPHIC|ZIP|XML|JSON|PDF|EXCEL|EX-101\.|EX-104)", re.I)
_DOC = re.compile(r"<DOCUMENT>(.*?)(?:</DOCUMENT>|\Z)", re.S)
_TAG = {k: re.compile(rf"^<{k}>(.*)$", re.M) for k in ("TYPE", "FILENAME", "DESCRIPTION")}
_TEXT = re.compile(r"<TEXT>(.*?)(?:</TEXT>|\Z)", re.S)
_XML = re.compile(r"<XML>\s*(.*?)\s*(?:</XML>|\Z)", re.S)


@dataclass
class Document:
    type: str
    filename: str
    description: str
    raw: str  # content between <TEXT> tags

    @property
    def is_xml(self) -> bool:
        return "<XML>" in self.raw[:200]

    @property
    def text(self) -> str:
        return html_to_text(self.raw) if "<" in self.raw else self.raw.strip()

    def xml_root(self) -> etree._Element:
        """Parsed XML with namespaces stripped, so callers can use plain tag names."""
        m = _XML.search(self.raw)
        if not m:
            raise ValueError(f"document {self.filename} has no <XML> block")
        root = etree.fromstring(m.group(1).encode(), parser=etree.XMLParser(recover=True, huge_tree=True))
        for el in root.iter():
            if isinstance(el.tag, str) and "}" in el.tag:
                el.tag = el.tag.split("}", 1)[1]
        return root


@dataclass
class Submission:
    accession: str
    form_type: str
    accepted_at: datetime | None
    period_of_report: str | None
    item_titles: list[str] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)

    def first(self, *types: str) -> Document | None:
        return next((d for d in self.documents if d.type in types), None)

    def of_prefix(self, prefix: str) -> list[Document]:
        return [d for d in self.documents if d.type.startswith(prefix)]


def read_submission_head(client: RateLimitedClient, entry: IndexEntry) -> str:
    lines: list[str] = []
    size = 0
    with closing(client.stream_lines(entry.submission_url)) as stream:
        for line in stream:
            if line.startswith("<TYPE>") and _STOP_TYPES.match(line[6:].strip()):
                break
            lines.append(line)
            size += len(line)
            if size > MAX_FILING_BYTES:
                log.warning("Filing %s exceeded %s bytes, truncating", entry.accession, MAX_FILING_BYTES)
                break
    return "\n".join(lines)


def parse_submission(text: str) -> Submission:
    header, _, rest = text.partition("</SEC-HEADER>")

    def h(pattern: str) -> str | None:
        m = re.search(pattern, header)
        return m.group(1).strip() if m else None

    accepted = h(r"<ACCEPTANCE-DATETIME>(\d{14})")
    sub = Submission(
        accession=h(r"ACCESSION NUMBER:\s*(\S+)") or "",
        form_type=h(r"CONFORMED SUBMISSION TYPE:\s*(.+)") or "",
        accepted_at=datetime.strptime(accepted, "%Y%m%d%H%M%S").replace(tzinfo=EASTERN) if accepted else None,
        period_of_report=h(r"CONFORMED PERIOD OF REPORT:\s*(\d{8})"),
        item_titles=[m.strip() for m in re.findall(r"ITEM INFORMATION:\s*(.+)", header)],
    )
    for raw in _DOC.findall(rest):

        def tag(name: str, raw: str = raw) -> str:
            m = _TAG[name].search(raw)
            return m.group(1).strip() if m else ""

        doc_type = tag("TYPE").upper()
        if not doc_type:
            continue  # the dangling <DOCUMENT> where streaming stopped
        body = _TEXT.search(raw)
        sub.documents.append(Document(doc_type, tag("FILENAME"), tag("DESCRIPTION"), body.group(1) if body else ""))
    return sub


def fetch_submission(client: RateLimitedClient, entry: IndexEntry) -> Submission:
    return parse_submission(read_submission_head(client, entry))
