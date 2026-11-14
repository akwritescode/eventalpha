"""Text helpers shared by sources."""

from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

_WS = re.compile(r"[ \t ]+")
_BLANKS = re.compile(r"\n{3,}")

# "(NYSE: ABC)", "(Nasdaq: XYZ)", "(NYSE American: FOO)", "(TSX: A, NYSE: B)"
_EXCHANGE_TICKER = re.compile(
    r"\b(?:NYSE(?:\s+American|\s+Arca)?|NASDAQ|Nasdaq(?:GS|GM|CM)?|AMEX|Cboe(?:\s+BZX)?)\s*:\s*"
    r"([A-Z]{1,5}(?:[.\-][A-Z])?)\b"
)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = (_WS.sub(" ", line).strip() for line in text.splitlines())
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip()


def extract_exchange_tickers(text: str) -> list[str]:
    """US-listed tickers that press releases cite next to the company name."""
    seen: dict[str, None] = {}
    for m in _EXCHANGE_TICKER.finditer(text):
        seen[m.group(1).replace("-", ".")] = None
    return list(seen)
