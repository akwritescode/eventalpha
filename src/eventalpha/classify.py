"""Jev (TypeSafe System One) classification.

One request per article; every question is answered in the same call, evaluated
independently against the same state. Output is typed (labels + probabilities), so
there is no free text to parse and nothing an article can inject into downstream code.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Question, Score, SystemOneResponse, TypeSafeError

log = logging.getLogger(__name__)

# Bump whenever QUESTIONS changes: scores are keyed on (model, questions_version), so a new
# version re-classifies history alongside the old scores instead of silently mixing them.
QUESTIONS_VERSION = "v1"

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
    "sentiment": Choice(
        instructions=(
            "You are a short-term equity trader. Judge the likely effect of this news on the "
            "share price of the company it is about over the next trading session."
        ),
        criteria={
            "bullish": "Likely to push the share price up: beats, raised outlook, favorable deals or rulings.",
            "bearish": "Likely to push the share price down: misses, cut outlook, dilution, losses, "
            "investigations, executive exits under pressure.",
            "neutral": "Routine or mixed, unlikely to move the price: scheduling notices, "
            "boilerplate filings, conference attendance.",
        },
    ),
    "materiality": Score(
        instructions="How material is this news to the company's valuation?",
        criteria=[
            "Routine: administrative or boilerplate, no new information",
            "Minor: small update, unlikely to matter to investors",
            "Moderate: relevant new information investors will note",
            "Major: likely to move the stock significantly",
        ],
    ),
    "company_specific": Noul(
        instructions="Is this news primarily about one specific publicly traded company?"
    ),
    **{f"event_{k}": Noul(instructions=v) for k, v in EVENT_QUESTIONS.items()},
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


def to_score_row(article_id: int, resp: SystemOneResponse) -> dict[str, Any]:
    sentiment = resp.choices["sentiment"]
    probs = {label: float(sentiment.probabilities.get(label, 0.0)) for label in SENTIMENT_LABELS}
    materiality = resp.scores["materiality"]
    return {
        "article_id": article_id,
        "model": resp.model,  # the concrete version that answered, e.g. "jev-1.14.0"
        "questions_version": QUESTIONS_VERSION,
        "sentiment": sentiment.choice,
        "p_bullish": probs["bullish"],
        "p_bearish": probs["bearish"],
        "p_neutral": probs["neutral"],
        "sentiment_score": probs["bullish"] - probs["bearish"],
        "sentiment_confidence": float(sentiment.confidence),
        "materiality": float(materiality.score),
        "materiality_confidence": float(materiality.confidence),
        "company_specific": float(resp.nouls["company_specific"].noul),
        "events": {k: round(float(resp.nouls[f"event_{k}"].noul), 4) for k in EVENT_QUESTIONS},
        "input_tokens": resp.usage.input_tokens,
    }


async def classify_articles(
    client: AsyncTypeSafeClient,
    articles: Sequence[Mapping[str, Any]],
    model: str,
    concurrency: int = 8,
) -> tuple[list[dict[str, Any]], list[int]]:
    """Classify concurrently. Returns (score rows, ids that failed after SDK retries)."""
    sem = asyncio.Semaphore(concurrency)

    async def one(article: Mapping[str, Any]) -> dict[str, Any] | None:
        async with sem:
            try:
                resp = await client.system_one(state=build_state(article), questions=QUESTIONS, model=model)
            except TypeSafeError as exc:
                log.warning("Jev failed for article %s: %s", article["id"], exc)
                return None
            return to_score_row(article["id"], resp)

    results = await asyncio.gather(*(one(a) for a in articles))
    rows = [r for r in results if r is not None]
    failed = [a["id"] for a, r in zip(articles, results, strict=True) if r is None]
    return rows, failed
