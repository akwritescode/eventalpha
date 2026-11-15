"""What we ask about every article, in provider-neutral terms.

A provider adapter (see providers/) translates these into its own API. Three question kinds
cover everything: pick one label, rate on an ordered scale, or yes/no with a probability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Bump whenever QUESTIONS changes: scores are keyed on (model, questions_version), so a new
# version re-classifies history alongside the old scores instead of silently mixing them.
QUESTIONS_VERSION = "v1"


@dataclass(frozen=True)
class ChoiceQuestion:
    """Pick exactly one label; the answer carries a probability per label."""

    instructions: str
    labels: Mapping[str, str]  # label -> what it means


@dataclass(frozen=True)
class ScaleQuestion:
    """Rate on ordered levels (index 0 = lowest); the answer is the expected level."""

    instructions: str
    levels: tuple[str, ...]


@dataclass(frozen=True)
class YesNoQuestion:
    """Probability that the statement is true."""

    instructions: str


Question = ChoiceQuestion | ScaleQuestion | YesNoQuestion

SENTIMENT_LABELS = ("bullish", "bearish", "neutral")

EVENT_QUESTIONS: dict[str, str] = {
    "earnings_results": "Does this report quarterly or annual financial results?",
    "guidance_raised": "Does the company raise its financial guidance or outlook?",
    "guidance_lowered": "Does the company lower, withdraw, or miss its financial guidance or outlook?",
    "m_and_a": "Does this announce a merger, acquisition, divestiture, or a definitive agreement for one?",
    "executive_change": "Does this announce the departure or appointment of a CEO, CFO, or other top executive?",
    "capital_raise": "Does this announce a stock offering, convertible notes, or other new financing?",
    "capital_return": "Does this announce a share buyback, a dividend change, or a special dividend?",
    "legal_regulatory": "Does this concern litigation, an investigation, a regulatory action, or an approval?",
    "restructuring": "Does this announce layoffs, restructuring, impairments, or facility closures?",
}

QUESTIONS: dict[str, Question] = {
    "sentiment": ChoiceQuestion(
        instructions=(
            "You are a short-term equity trader. Judge the likely effect of this news on the "
            "share price of the company it is about over the next trading session."
        ),
        labels={
            "bullish": "Likely to push the share price up: beats, raised outlook, favorable deals or rulings.",
            "bearish": "Likely to push the share price down: misses, cut outlook, dilution, losses, "
            "investigations, executive exits under pressure.",
            "neutral": "Routine or mixed, unlikely to move the price: scheduling notices, "
            "boilerplate filings, conference attendance.",
        },
    ),
    "materiality": ScaleQuestion(
        instructions="How material is this news to the company's valuation?",
        levels=(
            "Routine: administrative or boilerplate, no new information",
            "Minor: small update, unlikely to matter to investors",
            "Moderate: relevant new information investors will note",
            "Major: likely to move the stock significantly",
        ),
    ),
    "company_specific": YesNoQuestion("Is this news primarily about one specific publicly traded company?"),
    **{f"event_{k}": YesNoQuestion(v) for k, v in EVENT_QUESTIONS.items()},
}


def build_state(article: Mapping[str, Any]) -> str:
    """Article text plus metadata context the model can use to disambiguate."""
    lines = [f"Source: {article['source']}"]
    if article.get("company") or article.get("tickers"):
        tickers = ", ".join(article.get("tickers") or [])
        lines.append(f"Company: {article.get('company') or ''} {f'({tickers})' if tickers else ''}".rstrip())
    if article.get("form_type"):
        lines.append(f"SEC form: {article['form_type']}")
    if article.get("sec_items"):
        lines.append(f"SEC 8-K items: {', '.join(article['sec_items'])}")
    lines.append(f"Published: {article['published_at']:%Y-%m-%d %H:%M %Z}")
    lines.append(f"Title: {article['title']}")
    if article.get("summary") and article["summary"] != article["title"]:
        lines.append(f"Summary: {article['summary']}")
    if article.get("body"):
        lines.append("")
        lines.append(article["body"])
    return "\n".join(lines)
