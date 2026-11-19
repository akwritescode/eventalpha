"""Warehouse boundary for reviewed X leads. No raw post payload enters this interface."""

import re
from datetime import datetime

from sqlalchemy import Engine, func, select, update
from sqlalchemy.dialects.postgresql import insert

from eventalpha.schema import articles, x_leads


def record_lead(engine: Engine, *, post_id: str, ticker: str, paraphrase: str, published_at: datetime) -> None:
    """Record a brief reviewer-written paraphrase. Retries preserve the original observation."""
    ticker = ticker.strip().upper()
    paraphrase = paraphrase.strip()
    if not re.fullmatch(r"[1-9][0-9]{0,19}", post_id) or not re.fullmatch(r"[A-Z.\-]{1,10}", ticker):
        raise ValueError("Expected an X post ID and ticker")
    if not 1 <= len(paraphrase) <= 280 or published_at.utcoffset() is None:
        raise ValueError("Expected a brief paraphrase and an offset-aware publication time")
    stmt = insert(x_leads).values(post_id=post_id, ticker=ticker, paraphrase=paraphrase, published_at=published_at)
    with engine.begin() as conn:
        conn.execute(stmt.on_conflict_do_nothing(index_elements=[x_leads.c.post_id]))


def verify_lead(engine: Engine, *, post_id: str, source: str, source_id: str, supporting_passage: str) -> bool:
    """Record a review after a human checks that the cited original supports the paraphrase.

    The reviewer supplies a passage from the already-ingested original. A matching URL alone
    cannot verify a claim. Pin the review to the article version and keep the first decision.
    """
    passage = " ".join(supporting_passage.split())
    if not passage:
        raise ValueError("Expected a supporting passage from the reviewed original")
    with engine.begin() as conn:
        article = conn.execute(
            select(articles).where(articles.c.source == source, articles.c.source_id == source_id)
        ).one_or_none()
        if article is None or not any(
            passage in " ".join((part or "").split()) for part in (article.title, article.summary, article.body)
        ):
            return False

        verified_id = conn.scalar(
            update(x_leads)
            .where(
                x_leads.c.post_id == post_id,
                x_leads.c.article_id.is_(None),
                x_leads.c.ticker.in_(article.tickers),
            )
            .values(
                article_id=article.id,
                article_content_hash=article.content_hash,
                verified_at=func.statement_timestamp(),
            )
            .returning(x_leads.c.post_id)
        )
        return verified_id is not None
