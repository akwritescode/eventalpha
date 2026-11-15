"""Article classification, independent of which model provider does it."""

from eventalpha.classification.base import (
    Classification,
    Classifier,
    ClassifierError,
    classify_articles,
    to_score_row,
)
from eventalpha.classification.providers import create_classifier, resolve_model_id
from eventalpha.classification.questions import EVENT_QUESTIONS, QUESTIONS, QUESTIONS_VERSION, build_state

__all__ = [
    "EVENT_QUESTIONS",
    "QUESTIONS",
    "QUESTIONS_VERSION",
    "Classification",
    "Classifier",
    "ClassifierError",
    "build_state",
    "classify_articles",
    "create_classifier",
    "resolve_model_id",
    "to_score_row",
]
