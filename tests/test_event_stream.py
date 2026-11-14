from datetime import UTC, datetime

import fakeredis

from eventalpha.event_stream import STREAM, publish_alerts

ARTICLE = {
    "id": 2, "title": "AAON 8-K: Guidance cut", "tickers": ["AAON"], "form_type": "8-K",
    "source": "sec_edgar", "url": "https://example.com/2", "published_at": datetime(2026, 11, 13, 21, tzinfo=UTC),
}


def score(article_id: int, materiality: float, company_specific: float = 0.95) -> dict:
    return {
        "article_id": article_id, "sentiment": "bearish", "sentiment_score": -0.85, "materiality": materiality,
        "company_specific": company_specific, "model": "jev-1.14.0",
        "events": {"guidance_lowered": 0.95, "earnings_results": 0.8, "m_and_a": 0.01},
    }


def test_publishes_only_material_company_news_once():
    r = fakeredis.FakeRedis(decode_responses=True)
    routine = ARTICLE | {"id": 3}
    macro = ARTICLE | {"id": 4}
    scores = [score(2, 2.8), score(3, 1.0), score(4, 2.9, company_specific=0.2)]

    assert publish_alerts(r, [ARTICLE, routine, macro], scores) == 1
    assert publish_alerts(r, [ARTICLE, routine, macro], scores) == 0  # retried task: no duplicate

    [(entry_id, fields)] = r.xrange(STREAM)
    assert fields["article_id"] == "2" and fields["tickers"] == "AAON"
    assert fields["events"] == "guidance_lowered,earnings_results"  # by probability, >= 0.7 only
    assert fields["published_at"] == "2026-11-13T21:00:00+00:00"
