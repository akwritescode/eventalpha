"""Database code against a real Postgres 18, with the schema built by the Alembic migrations
(the same pattern as the API's Testcontainers tests). Needs Docker; without it the tests are
skipped locally and fail in CI (CI=true), so coverage never silently drops."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from eventalpha import db
from eventalpha.models import Article
from eventalpha.signals import inputs

MODEL, QV = "fake:model-1", "v1"


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    try:
        from testcontainers.community.postgres import PostgresContainer

        container = PostgresContainer("postgres:18", driver="psycopg").start()
    except Exception as exc:  # Docker not available
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Postgres container unavailable: {exc}")
    try:
        url = container.get_connection_url()
        from alembic import command
        from alembic.config import Config

        old = os.environ.get("EVENTALPHA_DATABASE_URL")
        os.environ["EVENTALPHA_DATABASE_URL"] = url
        try:
            command.upgrade(Config("alembic.ini"), "head")  # the real migrations, not create_all
        finally:
            if old is None:
                os.environ.pop("EVENTALPHA_DATABASE_URL", None)
            else:
                os.environ["EVENTALPHA_DATABASE_URL"] = old
        eng = db.make_engine(url)
        yield eng
        eng.dispose()
    finally:
        container.stop()


@pytest.fixture(autouse=True)
def clean(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles, article_scores, insider_transactions, econ_events CASCADE"))


def article(n: int, published: datetime, body: str = "text") -> Article:
    return Article(
        source="rss:test",
        source_id=f"item-{n}",
        url=f"https://example.com/{n}",
        title=f"Item {n}",
        body=body,
        published_at=published,
    )


def test_upsert_articles_inserts_then_updates_only_changed_content(engine: Engine):
    t = datetime(2026, 11, 13, 15, tzinfo=UTC)
    assert db.upsert_articles(engine, [article(1, t), article(2, t)]) == {"inserted": 2, "updated": 0}
    assert db.upsert_articles(engine, [article(1, t), article(2, t)]) == {"inserted": 0, "updated": 0}
    assert db.upsert_articles(engine, [article(1, t, body="revised"), article(3, t)]) == {"inserted": 1, "updated": 1}


def test_upsert_rows_overwrites_on_key_and_rejects_mixed_columns(engine: Engine):
    row = {
        "source": "bls",
        "event_key": "cpi-2026-11",
        "title": "CPI",
        "event_date": date(2026, 12, 10),
        "importance": "high",
    }
    assert db.upsert_rows(engine, "econ_events", [row], key=["source", "event_key"]) == 1
    db.upsert_rows(engine, "econ_events", [row | {"title": "Consumer Price Index"}], key=["source", "event_key"])
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM econ_events")).scalars().all() == ["Consumer Price Index"]
    with pytest.raises(ValueError, match="same columns"):
        db.upsert_rows(
            engine,
            "econ_events",
            [row, {k: v for k, v in row.items() if k != "importance"}],
            key=["source", "event_key"],
        )


def test_scoring_queue_takes_mostly_newest_but_drains_the_oldest(engine: Engine):
    start = datetime(2026, 11, 1, tzinfo=UTC)
    db.upsert_articles(engine, [article(n, start + timedelta(hours=n)) for n in range(8)])
    with engine.connect() as conn:
        by_n = dict(conn.execute(text("SELECT source_id, id FROM articles")).tuples().all())
    picked = db.select_unscored_ids(engine, MODEL, QV, limit=4)
    # 3 newest (items 7, 6, 5) + 1 oldest (item 0): the backlog still moves.
    assert picked == [by_n["item-7"], by_n["item-6"], by_n["item-5"], by_n["item-0"]]


def insider(acc: str, owner: str, traded: date, filed: datetime, ticker: str = "AAON") -> dict:
    return {
        "accession": acc,
        "row_no": 1,
        "form_type": "4",
        "issuer_cik": "1",
        "ticker": ticker,
        "owner_name": owner,
        "owner_count": 1,
        "is_director": True,
        "is_officer": False,
        "is_ten_percent_owner": False,
        "is_derivative": False,
        "transaction_date": traded,
        "transaction_code": "P",
        "shares": 10_000,
        "price": 50.0,
        "filed_at": filed,
    }


def test_late_filed_insider_purchase_is_kept_and_clusters_are_counted(engine: Engine):
    now = datetime.now(UTC)
    rows = [
        # Its own ticker, so no purchase of that stock falls in the 30-day cluster window.
        insider("a1", "Late Filer", (now - timedelta(days=40)).date(), now - timedelta(hours=2), ticker="LATE"),
        insider("b1", "Director One", (now - timedelta(days=3)).date(), now - timedelta(hours=3)),
    ]
    db.upsert_rows(engine, "insider_transactions", rows, key=["accession", "row_no"])
    buys = {b["owner_name"]: b for b in inputs.insider_buys(engine, now - timedelta(days=1))}
    assert set(buys) == {"Late Filer", "Director One"}
    assert buys["Late Filer"]["insiders_30d"] == 1
