"""Warehouse tables (SQLAlchemy Core). Alembic migrations are generated from this module,
and `alembic check` fails CI if the two drift."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

metadata = MetaData()

ticker_universe = Table(
    "ticker_universe",
    metadata,
    Column("ticker", String(16), primary_key=True),
    Column("cik", String(10), nullable=False, index=True),
    Column("name", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# ---------- ingestion ledger ----------

# One row per SEC filing a DAG processed, whatever the outcome. Answers "what did we get for
# 2026-11-13, what failed, and why" without reading task logs.
sec_filings = Table(
    "sec_filings",
    metadata,
    Column("accession", String(25), primary_key=True),
    Column("family", String(16), nullable=False),
    Column("form_type", String(20), nullable=False),
    Column("cik", String(10), nullable=False),
    Column("company", Text, nullable=False),
    Column("date_filed", Date, nullable=False),
    Column("status", String(10), nullable=False),  # loaded | skipped | failed
    Column("rows", Integer, nullable=False, server_default="0"),
    Column("detail", Text),
    Column("processed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_sec_filings_date_family", "date_filed", "family"),
)

# ---------- text events (8-K, 6-K, 13D, offerings) and RSS ----------

articles = Table(
    "articles",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("source", String(64), nullable=False),
    Column("source_id", Text, nullable=False),
    Column("form_type", String(20)),
    Column("url", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("summary", Text),
    Column("body", Text),
    Column("company", Text),
    Column("cik", String(10), index=True),
    Column("tickers", ARRAY(String(16)), nullable=False, server_default="{}"),
    Column("sec_items", ARRAY(String(8)), nullable=False, server_default="{}"),
    Column("published_at", DateTime(timezone=True), nullable=False, index=True),
    Column("content_hash", String(64), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("source", "source_id", name="uq_articles_source_source_id"),
    Index("ix_articles_tickers", "tickers", postgresql_using="gin"),
)

# One row per (article, model, question set). A new Jev version or a revised question set
# produces new rows instead of overwriting, so re-classifying history is just a backfill.
article_scores = Table(
    "article_scores",
    metadata,
    Column("article_id", BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("model", String(32), primary_key=True),
    Column("questions_version", String(16), primary_key=True),
    Column("sentiment", String(16), nullable=False),
    Column("p_bullish", Float, nullable=False),
    Column("p_bearish", Float, nullable=False),
    Column("p_neutral", Float, nullable=False),
    Column("sentiment_score", Float, nullable=False),  # p_bullish - p_bearish, in [-1, 1]
    Column("sentiment_confidence", Float, nullable=False),
    Column("materiality", Float, nullable=False),  # expected level, 0 (routine) .. 3 (major)
    Column("materiality_confidence", Float, nullable=False),
    Column("company_specific", Float, nullable=False),  # P(about one specific listed company)
    Column("events", JSONB, nullable=False),  # {"earnings_results": 0.97, "guidance_lowered": 0.02, ...}
    Column("input_tokens", Integer),
    Column("scored_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# Conditional-GET state per feed, so unchanged feeds cost a 304 instead of a full download.
feed_state = Table(
    "feed_state",
    metadata,
    Column("feed_url", Text, primary_key=True),
    Column("etag", Text),
    Column("last_modified", Text),
    Column("last_status", Integer),
    Column("last_fetched_at", DateTime(timezone=True)),
)

# ---------- Form 4 ----------

insider_transactions = Table(
    "insider_transactions",
    metadata,
    Column("accession", String(25), primary_key=True),
    Column("row_no", Integer, primary_key=True),
    Column("form_type", String(8), nullable=False),
    Column("issuer_cik", String(10), nullable=False),
    Column("ticker", String(16)),
    Column("issuer_name", Text),
    Column("owner_cik", String(10)),
    Column("owner_name", Text),
    Column("owner_count", Integer, nullable=False),
    Column("is_director", Boolean, nullable=False),
    Column("is_officer", Boolean, nullable=False),
    Column("is_ten_percent_owner", Boolean, nullable=False),
    Column("officer_title", Text),
    Column("is_derivative", Boolean, nullable=False),
    Column("security_title", Text),
    Column("transaction_date", Date),
    Column("transaction_code", String(2)),
    Column("shares", Numeric(24, 6)),
    Column("price", Numeric(18, 6)),
    Column("acquired_disposed", String(1)),
    Column("shares_owned_after", Numeric(24, 6)),
    Column("ownership", String(1)),  # D direct, I indirect
    Column("filed_at", DateTime(timezone=True)),
    Index("ix_insider_ticker_date", "ticker", "transaction_date"),
    Index("ix_insider_code_date", "transaction_code", "transaction_date"),
)

# ---------- 13F ----------

institutional_filings = Table(
    "institutional_filings",
    metadata,
    Column("accession", String(25), primary_key=True),
    Column("form_type", String(10), nullable=False),
    Column("filer_cik", String(10), nullable=False, index=True),
    Column("filer_name", Text, nullable=False),
    Column("period_of_report", Date, index=True),
    Column("amendment_type", String(20)),  # RESTATEMENT | NEW HOLDINGS (amendments only)
    Column("table_entry_total", Numeric(12, 0)),
    Column("table_value_total", Numeric(24, 0)),
)

institutional_holdings = Table(
    "institutional_holdings",
    metadata,
    Column("accession", String(25), ForeignKey("institutional_filings.accession", ondelete="CASCADE"),
           primary_key=True),
    Column("row_no", Integer, primary_key=True),
    Column("cusip", String(9), nullable=False),
    Column("issuer_name", Text),
    Column("title_of_class", Text),
    Column("value_usd", Numeric(24, 0)),
    Column("shares", Numeric(24, 0)),
    Column("share_type", String(4)),  # SH shares | PRN principal
    Column("put_call", String(4)),
    Column("investment_discretion", String(8)),
    Column("voting_sole", Numeric(24, 0)),
    Column("voting_shared", Numeric(24, 0)),
    Column("voting_none", Numeric(24, 0)),
    Index("ix_holdings_cusip", "cusip"),
)

# ---------- 10-K / 10-Q ----------

report_sections = Table(
    "report_sections",
    metadata,
    Column("accession", String(25), primary_key=True),
    Column("section", String(32), primary_key=True),  # risk_factors | mdna
    Column("cik", String(10), nullable=False),
    Column("form_type", String(8), nullable=False),
    Column("period_of_report", Date),
    Column("text", Text, nullable=False),
    Column("chars", Integer, nullable=False),
    Index("ix_report_sections_cik_period", "cik", "period_of_report"),
)

financial_facts = Table(
    "financial_facts",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("accession", String(25), nullable=False),
    Column("cik", String(10), nullable=False),
    Column("concept", String(96), nullable=False),  # "us-gaap:Revenues"
    Column("unit", String(24), nullable=False),  # USD, USD/shares, shares
    Column("period_start", Date),  # NULL for instant facts (balance sheet)
    Column("period_end", Date, nullable=False),
    Column("value", Numeric(28, 6), nullable=False),
    Column("fiscal_year", Integer),
    Column("fiscal_period", String(4)),  # FY, Q1..Q4
    Column("form_type", String(8)),
    Column("frame", String(16)),  # CY2026Q3 etc., set by SEC when the fact is the canonical one
    # NULLS NOT DISTINCT (Postgres 15+): instant facts have no start date but are still unique.
    UniqueConstraint("accession", "concept", "unit", "period_start", "period_end",
                     name="uq_financial_facts_fact", postgresql_nulls_not_distinct=True),
    Index("ix_financial_facts_cik_concept", "cik", "concept", "period_end"),
)
