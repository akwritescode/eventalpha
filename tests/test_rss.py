import feedparser

from eventalpha.sources.rss import Feed, entry_to_article
from eventalpha.text import extract_exchange_tickers

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Acme Reports Q3 Results</title><link>https://example.com/a</link><guid>g-1</guid>
<pubDate>Fri, 13 Nov 2026 22:40:00 +0000</pubDate>
<description><![CDATA[<p>NEW YORK -- Acme Corp (NYSE: ACME) and Beta (Nasdaq: BETA) today...</p>]]></description></item>
<item><title></title><link>https://example.com/b</link></item>
</channel></rss>"""


def test_entry_to_article():
    entries = feedparser.parse(FEED).entries
    a = entry_to_article(Feed("prn", "https://x"), entries[0])
    assert a.source == "rss:prn" and a.source_id == "g-1"
    assert a.tickers == ["ACME", "BETA"]
    assert a.published_at.isoformat() == "2026-11-13T22:40:00+00:00"
    assert entry_to_article(Feed("prn", "https://x"), entries[1]) is None  # no title


def test_ticker_extraction_variants():
    text = "(NYSE American: AMS) (NASDAQ:XYZ) (TSX: ABC, NYSE: BRK.B) (NYSE: BF-B)"
    assert extract_exchange_tickers(text) == ["AMS", "XYZ", "BRK.B", "BF.B"]
