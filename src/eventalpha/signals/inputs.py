"""Reads every input the signals use, each with the timestamp that says how fresh it is."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import Engine, text

LATEST_SCORES = """
    latest_scores AS (
        SELECT DISTINCT ON (article_id) *
        FROM article_scores
        ORDER BY article_id, scored_at DESC
    )"""


@dataclass
class ScoredArticle:
    id: int
    title: str
    url: str
    source: str
    form_type: str | None
    cik: str | None
    tickers: list[str]
    published_at: datetime
    sentiment: str
    sentiment_score: float
    materiality: float
    company_specific: float
    events: dict[str, float] = field(default_factory=dict)

    def top_events(self, threshold: float = 0.7) -> list[str]:
        return [k for k, p in sorted(self.events.items(), key=lambda kv: -kv[1]) if p >= threshold]


def scored_articles(engine: Engine, start: datetime, end: datetime) -> list[ScoredArticle]:
    sql = text(f"""
        WITH {LATEST_SCORES}
        SELECT a.id, a.title, a.url, a.source, a.form_type, a.cik, a.tickers, a.published_at,
               s.sentiment, s.sentiment_score, s.materiality, s.company_specific, s.events
        FROM articles a JOIN latest_scores s ON s.article_id = a.id
        WHERE a.published_at > :start AND a.published_at <= :end
        ORDER BY a.published_at""")
    with engine.connect() as conn:
        return [ScoredArticle(**dict(r._mapping)) for r in conn.execute(sql, {"start": start, "end": end})]


def unscored_count(engine: Engine, start: datetime, end: datetime) -> int:
    sql = text("""SELECT count(*) FROM articles a
                  WHERE a.published_at > :start AND a.published_at <= :end
                    AND NOT EXISTS (SELECT 1 FROM article_scores s WHERE s.article_id = a.id)""")
    with engine.connect() as conn:
        return int(conn.execute(sql, {"start": start, "end": end}).scalar_one())


def freshness(engine: Engine) -> dict[str, str | None]:
    """Newest timestamp per input, shown on every alert."""
    queries = {
        "articles_ingested": "SELECT max(ingested_at) FROM articles",
        "articles_scored": "SELECT max(scored_at) FROM article_scores",
        "sec_filing_processed": "SELECT max(processed_at) FROM sec_filings",
        "market_snapshot": "SELECT max(captured_at) FROM market_snapshots",
        "macro_observations": "SELECT max(fetched_at) FROM macro_observations",
        "inflation_nowcast": "SELECT max(vintage)::text FROM inflation_nowcasts",
        "econ_calendar": "SELECT max(fetched_at) FROM econ_events",
        "earnings_calendar": "SELECT max(fetched_at) FROM earnings_events",
    }
    out = {}
    with engine.connect() as conn:
        for k, q in queries.items():
            v = conn.execute(text(q)).scalar()
            out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def snapshot(engine: Engine, session_date: date, kind: str) -> dict[str, dict[str, Any]]:
    """Quotes taken for a signal, with the previous session's close from daily bars as a
    fallback: index quotes (SPX, VIX) report prev_close == last outside market hours."""
    sql = text("""
        SELECT m.symbol, m.last, m.prev_close, m.change_pct, m.captured_at,
               (SELECT b.close FROM price_bars_daily b
                WHERE b.symbol = m.symbol AND b.day < :d ORDER BY b.day DESC LIMIT 1) AS bar_prev_close
        FROM market_snapshots m WHERE m.session_date = :d AND m.kind = :k""")
    with engine.connect() as conn:
        return {r.symbol: dict(r._mapping) for r in conn.execute(sql, {"d": session_date, "k": kind})}


def econ_events_on(engine: Engine, day: date) -> list[dict[str, Any]]:
    sql = text("""SELECT title, scheduled_at, importance, source FROM econ_events
                  WHERE event_date = :d ORDER BY scheduled_at NULLS LAST, title""")
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql, {"d": day})]


def earnings_on(engine: Engine, day: date, tickers: list[str] | None = None) -> list[dict[str, Any]]:
    sql = "SELECT ticker, event_date, status, description FROM earnings_events WHERE event_date = :d"
    params: dict[str, Any] = {"d": day}
    if tickers is not None:
        sql += " AND ticker = ANY(:t)"
        params["t"] = tickers
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql + " ORDER BY ticker"), params)]


def insider_buys(engine: Engine, since: datetime, min_value: float = 100_000) -> list[dict[str, Any]]:
    """Open-market purchases (code P) filed since `since`, with how many distinct insiders
    bought the same stock in the last 30 days (clusters are the stronger signal)."""
    sql = text("""
        WITH recent AS (  -- one row per insider per stock, summing their purchases
            SELECT ticker, owner_name, max(officer_title) AS officer_title, bool_or(is_director) AS is_director,
                   bool_or(is_officer) AS is_officer, sum(shares) AS shares, sum(shares * price) AS value,
                   max(transaction_date) AS transaction_date, max(filed_at) AS filed_at
            FROM insider_transactions
            WHERE transaction_code = 'P' AND NOT is_derivative AND filed_at > :since AND ticker IS NOT NULL
            GROUP BY ticker, owner_name
            HAVING sum(shares * price) >= :min_value
        ), cluster AS (
            SELECT ticker, count(DISTINCT owner_name) AS insiders_30d
            FROM insider_transactions
            WHERE transaction_code = 'P' AND NOT is_derivative AND transaction_date >= current_date - 30
            GROUP BY ticker
        )
        SELECT r.*, c.insiders_30d FROM recent r JOIN cluster c USING (ticker)
        ORDER BY c.insiders_30d DESC, r.value DESC""")
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql, {"since": since, "min_value": min_value})]


def latest_macro(engine: Engine, source: str, series_id: str, n: int = 2) -> list[dict[str, Any]]:
    sql = text("""SELECT period, value FROM macro_observations
                  WHERE source = :s AND series_id = :id AND value IS NOT NULL
                  ORDER BY period DESC LIMIT :n""")
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql, {"s": source, "id": series_id, "n": n})]


def latest_nowcast(engine: Engine, horizon: str = "mom") -> list[dict[str, Any]]:
    """Newest vintage for each measure of the most recent target period, with the actual if out."""
    sql = text("""
        SELECT DISTINCT ON (measure) measure, target_period, vintage, value, actual
        FROM inflation_nowcasts
        WHERE horizon = :h AND target_period = (
            SELECT max(target_period) FROM inflation_nowcasts WHERE horizon = :h)
        ORDER BY measure, vintage DESC""")
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql, {"h": horizon})]


CPI_SA_SERIES = {"cpi": "CUSR0000SA0", "core_cpi": "CUSR0000SA0L1E"}


def cpi_surprises(engine: Engine, before: date) -> list[dict[str, Any]]:
    """Latest official CPI m/m (BLS, seasonally adjusted) vs the last Cleveland Fed nowcast made
    before `before` for that month. BLS publishes at 08:30 ET; the Cleveland Fed only fills in
    its own "actual" at its ~10:00 update, so the 09:15 signal computes the surprise itself."""
    out = []
    for measure, series in CPI_SA_SERIES.items():
        obs = latest_macro(engine, "bls", series, n=2)
        if len(obs) < 2 or not obs[1]["value"]:
            continue
        mom = (float(obs[0]["value"]) / float(obs[1]["value"]) - 1) * 100
        period = obs[0]["period"].strftime("%Y-%m")
        sql = text("""SELECT value, vintage FROM inflation_nowcasts
                      WHERE horizon = 'mom' AND measure = :m AND target_period = :p AND vintage < :before
                      ORDER BY vintage DESC LIMIT 1""")
        with engine.connect() as conn:
            nc = conn.execute(sql, {"m": measure, "p": period, "before": before}).first()
        if nc and nc.value is not None:
            out.append(
                {
                    "measure": measure,
                    "period": period,
                    "actual_mom": round(mom, 3),
                    "nowcast_mom": round(float(nc.value), 3),
                    "nowcast_vintage": nc.vintage.isoformat(),
                    "surprise": round(mom - float(nc.value), 3),
                }
            )
    return out
