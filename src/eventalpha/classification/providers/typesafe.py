"""TypeSafe System One provider (https://docs.typesafe.ai).

One request per article answers every question; each question is evaluated independently
against the same state. Answers are typed (labels and probabilities), so there's no free text
to parse. Reads TYPESAFE_API_KEY from the environment.
"""

from __future__ import annotations

from collections.abc import Mapping

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score, TypeSafeError

from eventalpha.classification.base import (
    ChoiceAnswer,
    Classification,
    ClassifierError,
    ScaleAnswer,
)
from eventalpha.classification.questions import ChoiceQuestion, Question, ScaleQuestion, YesNoQuestion

PROVIDER = "typesafe"
# Pin a concrete version: thresholds tuned on one version don't transfer to the next.
DEFAULT_MODEL = "jev-1.14.0"


def _to_provider(q: Question):
    match q:
        case ChoiceQuestion(instructions, labels):
            return Choice(instructions=instructions, criteria=dict(labels))
        case ScaleQuestion(instructions, levels):
            return Score(instructions=instructions, criteria=list(levels))
        case YesNoQuestion(instructions):
            return Noul(instructions=instructions)
    raise TypeError(f"unsupported question type {type(q).__name__}")


class TypeSafeClassifier:
    def __init__(self, model: str = DEFAULT_MODEL, client: AsyncTypeSafeClient | None = None) -> None:
        self._model = model
        self._client = client or AsyncTypeSafeClient()

    @property
    def model_id(self) -> str:
        return f"{PROVIDER}:{self._model}"

    async def classify(self, state: str, questions: Mapping[str, Question]) -> Classification:
        try:
            resp = await self._client.system_one(
                state=state, questions={k: _to_provider(q) for k, q in questions.items()}, model=self._model
            )
        except TypeSafeError as exc:
            raise ClassifierError(str(exc)) from exc
        return Classification(
            model_id=f"{PROVIDER}:{resp.model}",  # the version that actually answered
            choices={k: ChoiceAnswer(a.choice, dict(a.probabilities), a.confidence) for k, a in resp.choices.items()},
            scales={k: ScaleAnswer(a.score, a.confidence) for k, a in resp.scores.items()},
            yes_no={k: a.noul for k, a in resp.nouls.items()},
            input_tokens=resp.usage.input_tokens,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def create(model: str | None = None) -> TypeSafeClassifier:
    return TypeSafeClassifier(model or DEFAULT_MODEL)
