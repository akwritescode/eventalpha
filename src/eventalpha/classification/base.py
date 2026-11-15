"""The classifier interface and the provider-neutral scoring loop.

Pipeline code depends only on this module. A provider implements `Classifier`; nothing
outside `providers/` imports a vendor SDK.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from eventalpha.classification.questions import (
    EVENT_QUESTIONS,
    QUESTIONS,
    QUESTIONS_VERSION,
    SENTIMENT_LABELS,
    Question,
    build_state,
)

log = logging.getLogger(__name__)


class ClassifierError(Exception):
    """A provider failed for one item (after its own retries)."""


@dataclass(frozen=True)
class ChoiceAnswer:
    label: str
    probabilities: Mapping[str, float]
    confidence: float


@dataclass(frozen=True)
class ScaleAnswer:
    value: float  # expected level, 0 .. len(levels)-1
    confidence: float


@dataclass
class Classification:
    """One article's answers, in the same shape for every provider."""

    model_id: str  # "<provider>:<model version>"
    choices: dict[str, ChoiceAnswer] = field(default_factory=dict)
    scales: dict[str, ScaleAnswer] = field(default_factory=dict)
    yes_no: dict[str, float] = field(default_factory=dict)
    input_tokens: int | None = None


class Classifier(Protocol):
    @property
    def model_id(self) -> str:
        """Provider-qualified model id ("<provider>:<model>") that scores are stored under."""
        ...

    async def classify(self, state: str, questions: Mapping[str, Question]) -> Classification: ...

    async def aclose(self) -> None: ...


def to_score_row(article_id: int, result: Classification) -> dict[str, Any]:
    sentiment = result.choices["sentiment"]
    probs = {label: float(sentiment.probabilities.get(label, 0.0)) for label in SENTIMENT_LABELS}
    materiality = result.scales["materiality"]
    return {
        "article_id": article_id,
        "model": result.model_id,
        "questions_version": QUESTIONS_VERSION,
        "sentiment": sentiment.label,
        "p_bullish": probs["bullish"],
        "p_bearish": probs["bearish"],
        "p_neutral": probs["neutral"],
        "sentiment_score": probs["bullish"] - probs["bearish"],
        "sentiment_confidence": float(sentiment.confidence),
        "materiality": float(materiality.value),
        "materiality_confidence": float(materiality.confidence),
        "company_specific": float(result.yes_no["company_specific"]),
        "events": {k: round(float(result.yes_no[f"event_{k}"]), 4) for k in EVENT_QUESTIONS},
        "input_tokens": result.input_tokens,
    }


async def classify_articles(
    classifier: Classifier, articles: Sequence[Mapping[str, Any]], concurrency: int = 8
) -> tuple[list[dict[str, Any]], list[int]]:
    """Classify concurrently. Returns (score rows, ids that failed after provider retries)."""
    sem = asyncio.Semaphore(concurrency)

    async def one(article: Mapping[str, Any]) -> dict[str, Any] | None:
        async with sem:
            try:
                result = await classifier.classify(build_state(article), QUESTIONS)
            except ClassifierError as exc:
                log.warning("classification failed for article %s: %s", article["id"], exc)
                return None
            try:
                return to_score_row(article["id"], result)
            except (KeyError, TypeError, ValueError) as exc:
                # An answer missing a question (or with a malformed value) fails this article
                # only; raising here would cancel the whole gather and lose the batch.
                log.warning("incomplete classification for article %s: %r", article["id"], exc)
                return None

    results = await asyncio.gather(*(one(a) for a in articles))
    rows = [r for r in results if r is not None]
    failed = [a["id"] for a, r in zip(articles, results, strict=True) if r is None]
    return rows, failed
