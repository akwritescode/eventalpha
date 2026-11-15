"""Idempotent writes. Every load is an upsert keyed on a natural key, so retries and
backfills can run any number of times without creating duplicates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, create_engine, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from eventalpha.models import Article
from eventalpha.schema import article_scores, articles, feed_state, metadata, sec_filings, ticker_universe

if TYPE_CHECKING:
    from eventalpha.sec.families import Outcome
    from eventalpha.sec.index import IndexEntry

# Postgres caps a statement at 65,535 bind parameters; keep multi-row INSERTs well under it.
_MAX_PARAMS = 30_000


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def upsert_articles(engine: Engine, items: Sequence[Article]) -> dict[str, int]:
    """Insert new articles; update existing ones only if their content changed."""
    if not items:
        return {"inserted": 0, "updated": 0}
    rows = [a.model_dump() for a in items]
    # Duplicates inside one batch would make ON CONFLICT fail ("cannot affect row a second time").
    rows = list({(r["source"], r["source_id"]): r for r in rows}.values())
    stmt = insert(articles).values(rows)
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        constraint="uq_articles_source_source_id",
        set_={
            c: excluded[c]
            for c in (
                "form_type",
                "url",
                "title",
                "summary",
                "body",
                "company",
                "cik",
                "tickers",
                "sec_items",
                "published_at",
                "content_hash",
            )
        }
        | {"updated_at": func.now()},
        where=articles.c.content_hash != excluded.content_hash,
    ).returning(articles.c.id, (articles.c.ingested_at == articles.c.updated_at).label("is_new"))
    with engine.begin() as conn:
        result = conn.execute(stmt).all()
    inserted = sum(1 for r in result if r.is_new)
    return {"inserted": inserted, "updated": len(result) - inserted}


def upsert_ticker_universe(engine: Engine, rows: Iterable[dict[str, str]]) -> int:
    rows = list({r["ticker"]: r for r in rows}.values())
    if not rows:
        return 0
    stmt = insert(ticker_universe).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "cik": stmt.excluded.cik,
            "name": stmt.excluded.name,
            "size_rank": stmt.excluded.size_rank,
            "updated_at": func.now(),
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return len(rows)


def load_cik_map(engine: Engine) -> dict[str, tuple[str, list[str]]]:
    """cik -> (company name, [tickers]). One CIK can list several share classes (GOOG, GOOGL)."""
    out: dict[str, tuple[str, list[str]]] = {}
    with engine.connect() as conn:
        for ticker, cik, name in conn.execute(
            select(ticker_universe.c.ticker, ticker_universe.c.cik, ticker_universe.c.name)
        ):
            out.setdefault(cik, (name, []))[1].append(ticker)
    return out


def select_unscored_ids(engine: Engine, model: str, questions_version: str, limit: int) -> list[int]:
    """Mostly newest first (signals need fresh news), with a quarter of each batch taken from the
    oldest end, so a backlog drains even while new articles keep arriving faster than the limit."""
    scored = (
        select(article_scores.c.article_id)
        .where(article_scores.c.model == model)
        .where(article_scores.c.questions_version == questions_version)
    )
    unscored = select(articles.c.id).where(articles.c.id.not_in(scored))
    oldest_n = limit // 4
    with engine.connect() as conn:
        newest = [r.id for r in conn.execute(unscored.order_by(articles.c.published_at.desc()).limit(limit - oldest_n))]
        oldest = [
            r.id
            for r in conn.execute(
                unscored.where(articles.c.id.not_in(newest)).order_by(articles.c.published_at.asc()).limit(oldest_n)
            )
        ]
    return newest + oldest


def load_articles(engine: Engine, ids: Sequence[int]) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(articles).where(articles.c.id.in_(ids)))]


def upsert_scores(engine: Engine, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    stmt = insert(article_scores).values(list(rows))
    pk = {"article_id", "model", "questions_version"}
    stmt = stmt.on_conflict_do_update(
        index_elements=sorted(pk),
        set_={c.name: stmt.excluded[c.name] for c in article_scores.columns if c.name not in pk},
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return len(rows)


def get_feed_state(engine: Engine, url: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(select(feed_state).where(feed_state.c.feed_url == url)).first()
    return dict(row._mapping) if row else None


def save_feed_state(engine: Engine, url: str, etag: str | None, last_modified: str | None, status: int) -> None:
    values = {
        "feed_url": url,
        "etag": etag,
        "last_modified": last_modified,
        "last_status": status,
        "last_fetched_at": datetime.now(UTC),
    }
    stmt = insert(feed_state).values(values)
    stmt = stmt.on_conflict_do_update(index_elements=["feed_url"], set_=values)
    with engine.begin() as conn:
        conn.execute(stmt)


def _insert_chunks(conn, table, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    per = max(1, _MAX_PARAMS // max(len(rows[0]), 1))
    for i in range(0, len(rows), per):
        conn.execute(insert(table).values(list(rows[i : i + per])))


def upsert_rows(engine: Engine, table_name: str, rows: Sequence[Mapping[str, Any]], key: Sequence[str]) -> int:
    """Insert-or-update on the given unique key (all non-key columns overwritten)."""
    if not rows:
        return 0
    columns = set(rows[0])
    if any(set(r) != columns for r in rows):
        # A multi-row INSERT takes its column list from the first row; refuse mismatched rows
        # with a clear error instead of an obscure one from SQLAlchemy.
        raise ValueError(f"upsert_rows({table_name}): every row must have the same columns")
    table = metadata.tables[table_name]
    stmt = insert(table).values(list(rows))
    stmt = stmt.on_conflict_do_update(
        index_elements=list(key),
        set_={c: stmt.excluded[c] for c in rows[0] if c not in key},
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return len(rows)


def replace_by_accession(
    engine: Engine, table_name: str, accessions: Sequence[str], rows: Sequence[Mapping[str, Any]]
) -> int:
    """Delete every row of these filings, then insert the new set, in one transaction.

    Upserts can't remove rows that a re-parse no longer produces (an amended filing with
    fewer lines), so child tables are replaced per filing instead. Same idempotency, no orphans.
    """
    if not accessions:
        return 0
    table = metadata.tables[table_name]
    with engine.begin() as conn:
        conn.execute(delete(table).where(table.c.accession.in_(list(accessions))))
        _insert_chunks(conn, table, rows)
    return len(rows)


def record_filings(engine: Engine, family: str, entries: Sequence[IndexEntry], outcomes: Mapping[str, Outcome]) -> None:
    rows = [
        {
            "accession": e.accession,
            "family": family,
            "form_type": e.form_type,
            "cik": e.cik,
            "company": e.company,
            "date_filed": e.date_filed,
            "status": outcomes[e.accession].status,
            "rows": outcomes[e.accession].rows,
            "detail": outcomes[e.accession].detail,
            "processed_at": datetime.now(UTC),
        }
        for e in entries
        if e.accession in outcomes
    ]
    upsert_rows(engine, sec_filings.name, rows, key=["accession"])
