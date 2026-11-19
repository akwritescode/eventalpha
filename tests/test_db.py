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


def test_x_lead_requires_reviewed_article_and_preserves_first_observation(engine: Engine):
    from eventalpha.sources.x import record_lead, verify_lead

    published = datetime(2025, 4, 15, 21, 22, tzinfo=UTC)
    primary = article(1, published, "NVIDIA disclosed a new export license requirement.").model_copy(
        update={"tickers": ["NVDA"]}
    )
    db.upsert_articles(engine, [primary])
    lead = {"post_id": "1001", "ticker": "NVDA", "published_at": published}
    record_lead(engine, **lead, paraphrase="NVIDIA reported a new export license requirement.")
    record_lead(engine, **lead, paraphrase="This retry must leave the original observation intact.")
    review = {"post_id": "1001", "source": primary.source, "source_id": primary.source_id}

    assert not verify_lead(engine, **review, supporting_passage="An unsupported claim.")
    assert verify_lead(engine, **review, supporting_passage="a new export license requirement.")
    assert not verify_lead(engine, **review, supporting_passage="a new export license requirement.")

    with engine.connect() as conn:
        saved = conn.execute(text("SELECT * FROM x_leads WHERE post_id = '1001'")).one()
        assert saved.paraphrase == "NVIDIA reported a new export license requirement."
        assert saved.published_at == published
        assert saved.verified_at >= saved.first_seen_at > published
        assert saved.article_content_hash == primary.content_hash
        assert conn.scalar(text("SELECT count(*) FROM articles")) == 1


class MemoryArchive:
    def __init__(self, corrupt=False):
        self.objects = {}
        self.corrupt = corrupt

    def upload_fileobj(self, file, bucket, key, **kwargs):
        self.objects[(bucket, key)] = file.read()

    def download_fileobj(self, bucket, key, file):
        body = self.objects[(bucket, key)]
        file.write(body + b"corruption" if self.corrupt else body)

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):
        import io

        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


@pytest.mark.parametrize("corrupt", [False, True])
def test_minute_archive_verifies_before_dropping_only_old_daily_partitions(engine: Engine, corrupt):
    import gzip
    import json

    from eventalpha.marketdata.storage import ensure_partitions, offload_minutes, partition_name, store_bars

    now = datetime.now(UTC)
    old_day = now.date() - timedelta(days=16)
    retained_day = now.date() - timedelta(days=14)
    ensure_partitions(engine, old_day, retained_day)
    old_ts = datetime.combine(old_day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=15)
    retained_ts = datetime.combine(retained_day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=15)
    store_bars(
        engine,
        [
            {"symbol": "AMD", "started_at": ts, "open": 100, "close": 102, "high": 103, "low": 99, "volume": 1234}
            for ts in (old_ts, retained_ts)
        ],
    )
    with engine.connect() as conn:
        original_seen = conn.scalar(
            text("SELECT first_seen_at FROM price_bars_minute WHERE symbol = 'AMD' AND started_at = :ts"),
            {"ts": old_ts},
        )
    store_bars(engine, [{"symbol": "AMD", "started_at": old_ts, "open": 999, "close": 999}])
    with engine.connect() as conn:
        saved = conn.execute(
            text("SELECT open, close, first_seen_at FROM price_bars_minute WHERE symbol = 'AMD' AND started_at = :ts"),
            {"ts": old_ts},
        ).one()
        assert saved.open == 100 and saved.close == 102 and saved.first_seen_at == original_seen

    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO price_bars_daily (symbol, day, open, high, low, close, source)
            VALUES ('ARCHIVE_TEST', :day, 100, 103, 99, 102, 'test')
        """),
            {"day": old_day},
        )
    archive = MemoryArchive(corrupt)
    production_manifest = ("test-bucket", f"minute_bars/dt={old_day.isoformat()}/_manifest.json")
    archive.objects[production_manifest] = b'{"environment":"production"}'
    try:
        if corrupt:
            with pytest.raises(ValueError, match="checksum"):
                offload_minutes(engine, archive, "test-bucket", now)
            with engine.connect() as conn:
                assert (
                    conn.scalar(text("SELECT count(*) FROM price_bars_minute WHERE started_at = :ts"), {"ts": old_ts})
                    == 1
                )
                assert conn.scalar(text("SELECT to_regclass(:part)"), {"part": partition_name(old_day)})
        else:
            result = offload_minutes(engine, archive, "test-bucket", now, prefix="minute_bars/local")
            exported = next(item for item in result["archived"] if item["day"] == old_day.isoformat())
            assert exported["key"].startswith("minute_bars/local/")
            assert archive.objects[production_manifest] == b'{"environment":"production"}'
            rows = [
                json.loads(line)
                for line in gzip.decompress(archive.objects[("test-bucket", exported["key"])]).splitlines()
            ]
            assert rows[0]["symbol"] == "AMD" and rows[0]["volume"] == 1234
            assert rows[0]["high"] == "103"
            assert "first_seen_at" in rows[0]
            with engine.connect() as conn:
                assert conn.scalar(text("SELECT to_regclass(:part)"), {"part": partition_name(old_day)}) is None
        with engine.connect() as conn:
            assert (
                conn.scalar(text("SELECT count(*) FROM price_bars_minute WHERE started_at = :ts"), {"ts": retained_ts})
                == 1
            )
            assert conn.scalar(text("SELECT close FROM price_bars_daily WHERE symbol = 'ARCHIVE_TEST'")) == 102
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE price_bars_minute"))
            conn.execute(text("DELETE FROM price_bars_daily WHERE symbol = 'ARCHIVE_TEST'"))


def test_minute_partition_migration_preserves_existing_candles(engine: Engine):
    from alembic import command
    from alembic.config import Config

    old = os.environ.get("EVENTALPHA_DATABASE_URL")
    os.environ["EVENTALPHA_DATABASE_URL"] = engine.url.render_as_string(hide_password=False)
    try:
        command.downgrade(Config("alembic.ini"), "78d93c0ea314")
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO price_bars_minute (symbol, started_at, open, close)
                VALUES ('AMD', now() - interval '3 days', 100, 101)
            """)
            )
        command.upgrade(Config("alembic.ini"), "head")
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM price_bars_minute WHERE symbol = 'AMD'")) == 1
            assert conn.scalar(text("SELECT relkind FROM pg_class WHERE oid = 'price_bars_minute'::regclass")) == "p"
            assert conn.scalar(text("SELECT count(*) FROM price_bars_minute_default")) == 0
        command.check(Config("alembic.ini"))
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE price_bars_minute"))
        if old is None:
            os.environ.pop("EVENTALPHA_DATABASE_URL", None)
        else:
            os.environ["EVENTALPHA_DATABASE_URL"] = old


def test_collection_universe_uses_reviewed_snapshot_without_network(engine: Engine, monkeypatch):
    import json
    from pathlib import Path

    import httpx

    from eventalpha.marketdata import universe

    snapshot = Path("config/candle_universe.json")
    data = json.loads(snapshot.read_text())
    members = {name: data[name] for name in ("sp500", "nasdaq100")}

    def unexpected_request(*args, **kwargs):
        raise AssertionError("Constituent collection must not make HTTP requests")

    monkeypatch.setattr(httpx.Client, "request", unexpected_request)
    now = datetime.now(UTC)
    try:
        symbols = universe.collection_symbols(engine, snapshot, now)
        assert symbols == sorted(set(members["sp500"] + members["nasdaq100"]) | universe.BENCHMARKS)
        assert "AMD" in symbols and "MU" in symbols and "BRK-B" in symbols
        with engine.connect() as conn:
            original_versions = conn.execute(
                text("SELECT index_name, symbol, xmin::text FROM minute_universe_members ORDER BY 1, 2")
            ).all()

        assert universe.collection_symbols(engine, snapshot, now + timedelta(days=1)) == symbols
        with engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT index_name, symbol, xmin::text FROM minute_universe_members ORDER BY 1, 2")
                ).all()
                == original_versions
            )
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM minute_universe_members")) == sum(map(len, members.values()))
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE minute_universe_members"))


def test_partition_creation_moves_overlapping_default_rows(engine: Engine):
    from eventalpha.marketdata.storage import ensure_partitions, partition_name, store_bars

    day = datetime.now(UTC).date() + timedelta(days=90)
    ts = datetime.combine(day, datetime.min.time(), UTC)
    store_bars(engine, [{"symbol": "DEFAULT_TEST", "started_at": ts, "open": 100, "close": 101}])
    with engine.connect() as conn:
        original = conn.execute(text("SELECT * FROM price_bars_minute_default WHERE symbol = 'DEFAULT_TEST'")).one()
    try:
        ensure_partitions(engine, day, day)
        with engine.connect() as conn:
            assert (
                conn.scalar(text("SELECT count(*) FROM price_bars_minute_default WHERE symbol = 'DEFAULT_TEST'")) == 0
            )
            moved = conn.execute(text(f"SELECT * FROM {partition_name(day)} WHERE symbol = 'DEFAULT_TEST'")).one()
            assert moved == original
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM price_bars_minute WHERE symbol = 'DEFAULT_TEST'"))


def test_archive_detects_late_insert_without_locking_network_transfer(engine: Engine):
    from eventalpha.marketdata.storage import ensure_partitions, offload_minutes, partition_name, store_bars

    now = datetime.now(UTC)
    day = now.date() - timedelta(days=16)
    ts = datetime.combine(day, datetime.min.time(), UTC)
    ensure_partitions(engine, day, day)
    store_bars(engine, [{"symbol": "BEFORE", "started_at": ts, "open": 100, "close": 101}])

    class LateInsertArchive(MemoryArchive):
        def upload_fileobj(self, file, bucket, key, ExtraArgs):
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '1s'"))
                conn.execute(
                    text(
                        "INSERT INTO price_bars_minute (symbol, started_at, open, close) VALUES ('LATE', :ts, 100, 101) ON CONFLICT DO NOTHING"
                    ),
                    {"ts": ts},
                )
            super().upload_fileobj(file, bucket, key, ExtraArgs=ExtraArgs)

    try:
        with pytest.raises(ValueError, match="changed during archive"):
            offload_minutes(engine, LateInsertArchive(False), "test-bucket", now)
        with engine.connect() as conn:
            assert conn.scalar(text(f"SELECT count(*) FROM {partition_name(day)}")) >= 2
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE price_bars_minute"))


def test_archive_repairs_an_old_default_partition_date(engine: Engine):
    from eventalpha.marketdata.storage import offload_minutes, store_bars

    now = datetime.now(UTC)
    day = now.date() - timedelta(days=100)
    ts = datetime.combine(day, datetime.min.time(), UTC)
    store_bars(engine, [{"symbol": "STRANDED", "started_at": ts, "open": 100, "close": 101}])
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM price_bars_minute_default WHERE symbol = 'STRANDED'")) == 1
    result = offload_minutes(engine, MemoryArchive(), "test-bucket", now)
    archived = next(row for row in result["archived"] if row["day"] == day.isoformat())
    assert archived["rows"] == 1
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM price_bars_minute_default")) == 0
