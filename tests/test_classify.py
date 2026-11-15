import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from eventalpha.classification import (
    EVENT_QUESTIONS,
    QUESTIONS,
    Classification,
    ClassifierError,
    build_state,
    classify_articles,
    resolve_model_id,
    to_score_row,
)
from eventalpha.classification.base import ChoiceAnswer, ScaleAnswer
from eventalpha.classification.providers import typesafe

ARTICLE = {
    "id": 7, "source": "sec_edgar", "company": "AAON, INC.", "tickers": ["AAON"], "sec_items": ["2.02"],
    "form_type": "8-K", "published_at": datetime(2026, 11, 13, 21, 0, tzinfo=UTC), "title": "AAON 8-K",
    "summary": None, "body": "Record revenue.",
}


def neutral_result(model_id: str = "fake:model-1") -> Classification:
    return Classification(
        model_id=model_id,
        choices={"sentiment": ChoiceAnswer("bullish", {"bullish": 0.7, "bearish": 0.1, "neutral": 0.2}, 0.6)},
        scales={"materiality": ScaleAnswer(2.4, 0.5)},
        yes_no={"company_specific": 0.9} | {f"event_{k}": 0.1 for k in EVENT_QUESTIONS},
        input_tokens=321,
    )


class FakeClassifier:
    model_id = "fake:model-1"

    async def classify(self, state, questions):
        if "fail" in state:
            raise ClassifierError("rate limited")
        return neutral_result()

    async def aclose(self):
        pass


def test_score_row_is_provider_neutral():
    row = to_score_row(7, neutral_result())
    assert row["model"] == "fake:model-1"
    assert row["sentiment_score"] == 0.7 - 0.1
    assert set(row["events"]) == set(EVENT_QUESTIONS)


def test_state_includes_context():
    state = build_state(ARTICLE)
    assert "Company: AAON, INC. (AAON)" in state and "SEC form: 8-K" in state and "SEC 8-K items: 2.02" in state
    assert state.endswith("Record revenue.")


def test_failures_are_reported_not_raised():
    bad = ARTICLE | {"id": 8, "body": "fail"}
    rows, failed = asyncio.run(classify_articles(FakeClassifier(), [ARTICLE, bad]))
    assert [r["article_id"] for r in rows] == [7] and failed == [8]


def test_model_ids_are_provider_qualified():
    assert resolve_model_id("typesafe") == f"typesafe:{typesafe.DEFAULT_MODEL}"
    assert resolve_model_id("typesafe", "jev-1.13.0") == "typesafe:jev-1.13.0"


def test_typesafe_adapter_maps_questions_and_answers():
    sent = {}

    class FakeSDK:
        async def system_one(self, state, questions, model):
            sent.update(questions=questions, model=model)
            nouls = {k: SimpleNamespace(noul=0.9) for k in questions if k not in ("sentiment", "materiality")}
            return SimpleNamespace(
                model="jev-1.14.0",
                usage=SimpleNamespace(input_tokens=100),
                choices={"sentiment": SimpleNamespace(choice="bearish", confidence=0.8,
                                                      probabilities={"bullish": 0.05, "bearish": 0.9, "neutral": 0.05})},
                scores={"materiality": SimpleNamespace(score=2.8, confidence=0.7)},
                nouls=nouls,
            )

    clf = typesafe.TypeSafeClassifier(client=FakeSDK())
    result = asyncio.run(clf.classify("state", QUESTIONS))
    assert sent["model"] == typesafe.DEFAULT_MODEL
    assert type(sent["questions"]["sentiment"]).__name__ == "Choice"
    assert type(sent["questions"]["materiality"]).__name__ == "Score"
    assert type(sent["questions"]["company_specific"]).__name__ == "Noul"
    row = to_score_row(1, result)
    assert row["model"] == "typesafe:jev-1.14.0" and row["sentiment"] == "bearish" and row["materiality"] == 2.8
