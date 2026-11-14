import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from typesafe_sdk import TypeSafeError

from eventalpha.classify import EVENT_QUESTIONS, QUESTIONS, build_state, classify_articles, to_score_row

ARTICLE = {
    "id": 7, "source": "edgar_8k", "company": "AAON, INC.", "tickers": ["AAON"], "sec_items": ["2.02"],
    "published_at": datetime(2026, 11, 13, 21, 0, tzinfo=UTC), "title": "AAON 8-K", "summary": None,
    "body": "Record revenue.",
}


def fake_response():
    nouls = {"company_specific": SimpleNamespace(noul=0.9)} | {
        f"event_{k}": SimpleNamespace(noul=0.1) for k in EVENT_QUESTIONS
    }
    return SimpleNamespace(
        model="jev-1.14.0",
        usage=SimpleNamespace(input_tokens=321),
        choices={"sentiment": SimpleNamespace(
            choice="bullish", confidence=0.6, probabilities={"bullish": 0.7, "bearish": 0.1, "neutral": 0.2})},
        scores={"materiality": SimpleNamespace(score=2.4, confidence=0.5)},
        nouls=nouls,
    )


def test_every_question_is_mapped():
    row = to_score_row(7, fake_response())
    assert row["sentiment_score"] == 0.7 - 0.1
    assert set(row["events"]) == set(EVENT_QUESTIONS)
    assert set(QUESTIONS) == {"sentiment", "materiality", "company_specific"} | {
        f"event_{k}" for k in EVENT_QUESTIONS
    }


def test_state_includes_context():
    state = build_state(ARTICLE)
    assert "Company: AAON, INC. (AAON)" in state and "SEC 8-K items: 2.02" in state
    assert state.endswith("Record revenue.")


def test_failures_are_reported_not_raised():
    class Client:
        async def system_one(self, state, questions, model):
            if "fail" in state:
                raise TypeSafeError("rate limited")
            return fake_response()

    bad = ARTICLE | {"id": 8, "body": "fail"}
    rows, failed = asyncio.run(classify_articles(Client(), [ARTICLE, bad], model="jev-1.14.0"))
    assert [r["article_id"] for r in rows] == [7] and failed == [8]
