"""Builds the two signals from warehouse data. Rules are deliberately simple and transparent:
every number in an alert traces back to rows a reader can query. Weights are starting guesses
until the evaluation job measures how well each component predicted the next session.

Both are research signals, not trading advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine

from eventalpha.signals import inputs
from eventalpha.signals.universe import Universe

MIN_COMPANY_SPECIFIC = 0.8
MIN_MATERIALITY = 1.5  # 0 routine .. 3 major
MEGACAP_WEIGHT = 0.6  # share of the SPX score from top-50 news; the rest is breadth
TOP_TICKERS = 15


@dataclass
class Signal:
    signal_type: str
    session_date: date
    generated_at: datetime
    score: float | None
    confidence: float | None
    payload: dict[str, Any] = field(default_factory=dict)
    inputs_as_of: dict[str, Any] = field(default_factory=dict)

    def row(self) -> dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "session_date": self.session_date,
            "generated_at": self.generated_at,
            "score": self.score,
            "confidence": self.confidence,
            "payload": self.payload,
            "inputs_as_of": self.inputs_as_of,
        }


def _json(obj: Any) -> Any:
    """Recursively make a payload JSON-safe (Decimal → float, dates → ISO strings)."""
    if isinstance(obj, dict):
        return {k: _json(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_json(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, date | datetime):
        return obj.isoformat()
    return obj


def _clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


def _weighted(items: list[tuple[float, float]]) -> float | None:
    """Weighted mean of (value, weight) pairs, None if there's no weight."""
    total = sum(w for _, w in items)
    return sum(v * w for v, w in items) / total if total else None


def _article_brief(a: inputs.ScoredArticle) -> dict[str, Any]:
    return {
        "tickers": a.tickers,
        "title": a.title,
        "url": a.url,
        "form_type": a.form_type,
        "sentiment": a.sentiment,
        "sentiment_score": round(a.sentiment_score, 3),
        "materiality": round(a.materiality, 2),
        "events": a.top_events(),
        "published_at": a.published_at.isoformat(),
    }


def _market_moves(snap: dict[str, dict[str, Any]], context: dict[str, str]) -> list[dict[str, Any]]:
    moves = []
    for sym, label in context.items():
        q = snap.get(sym)
        if not q or q.get("last") is None:
            continue
        chg = q.get("change_pct")
        prev = q.get("prev_close")
        if prev is None or float(prev) == float(q["last"]):  # index quotes after hours: use daily bars
            prev = q.get("bar_prev_close")
            chg = (float(q["last"]) / float(prev) - 1) * 100 if prev else chg
        moves.append(
            {
                "symbol": sym,
                "label": label,
                "last": float(q["last"]),
                "change_pct": round(float(chg), 2) if chg is not None else None,
            }
        )
    return moves


def _econ_brief(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": e["title"],
            "importance": e["importance"],
            "time": e["scheduled_at"].strftime("%H:%M") if e["scheduled_at"] else None,
        }
        for e in events
    ]


# ---------- 16:45 SPX overnight ----------


def build_spx_overnight(
    engine: Engine,
    universe: Universe,
    session_date: date,
    window_start: datetime,
    now: datetime,
    next_session: date | None,
) -> Signal:
    articles = inputs.scored_articles(engine, window_start, now)
    company_news = [a for a in articles if a.company_specific >= MIN_COMPANY_SPECIFIC]

    by_cik, by_ticker = universe.by_cik(), universe.by_ticker()
    megacap: list[tuple[inputs.ScoredArticle, Any]] = []
    for a in company_news:
        company = by_cik.get(a.cik or "") or next((by_ticker[t] for t in a.tickers if t in by_ticker), None)
        if company:
            megacap.append((a, company))

    # Top-50 news: each article's sentiment weighted by market-cap weight × materiality.
    mega_score = _weighted([(a.sentiment_score, c.weight * a.materiality / 3) for a, c in megacap])
    # Breadth: every company-specific article, weighted by materiality.
    breadth_score = _weighted([(a.sentiment_score, a.materiality / 3) for a in company_news])
    parts = [(mega_score, MEGACAP_WEIGHT), (breadth_score, 1 - MEGACAP_WEIGHT)]
    present = [(v, w) for v, w in parts if v is not None]
    combined = _weighted(present) if present else None
    score = _clip(combined) if combined is not None else None

    unscored = inputs.unscored_count(engine, window_start, now)
    coverage = len(articles) / (len(articles) + unscored) if (articles or unscored) else 0.0
    # Confidence needs both: enough news overall, and news from the companies that move the index.
    breadth_cov = min(1.0, len(company_news) / 40)
    megacap_cov = min(1.0, len({c.cik for _, c in megacap}) / 5)
    confidence = round(coverage * (0.4 * breadth_cov + 0.6 * megacap_cov), 2) if score is not None else 0.0

    universe_tickers = [t for c in universe.companies for t in c.tickers]
    tomorrow_events = inputs.econ_events_on(engine, next_session) if next_session else []
    payload = {
        "window": {"start": window_start.isoformat(), "end": now.isoformat()},
        "components": {
            "megacap_news": mega_score and round(mega_score, 3),
            "breadth": breadth_score and round(breadth_score, 3),
            "megacap_weight": MEGACAP_WEIGHT,
        },
        "counts": {
            "articles_scored": len(articles),
            "company_specific": len(company_news),
            "megacap_articles": len(megacap),
            "unscored": unscored,
        },
        "megacap_news": [
            _article_brief(a) | {"company": c.name, "cap_weight": c.weight}
            for a, c in sorted(megacap, key=lambda ac: -ac[1].weight * ac[0].materiality)[:10]
        ],
        "earnings_today": inputs.earnings_on(engine, session_date, universe_tickers),
        "earnings_next_session": inputs.earnings_on(engine, next_session, universe_tickers) if next_session else [],
        "macro_next_session": _econ_brief(tomorrow_events),
        "macro_risk_next_session": any(e["importance"] == "high" for e in tomorrow_events),
        "inflation_nowcast": inputs.latest_nowcast(engine),
        "market_close": _market_moves(inputs.snapshot(engine, session_date, "close"), universe.context_symbols),
        "universe_as_of": universe.as_of,
    }
    return Signal("spx_overnight", session_date, now, score, confidence, _json(payload), inputs.freshness(engine))


# ---------- 09:15 premarket ----------


def build_premarket(
    engine: Engine, universe: Universe, session_date: date, window_start: datetime, now: datetime
) -> Signal:
    articles = [
        a
        for a in inputs.scored_articles(engine, window_start, now)
        if a.company_specific >= MIN_COMPANY_SPECIFIC and a.materiality >= MIN_MATERIALITY and a.tickers
    ]

    # One entry per company: its strongest item (materiality × strength of sentiment).
    def strength(a: inputs.ScoredArticle) -> float:
        return a.materiality * abs(a.sentiment_score)

    best: dict[str, inputs.ScoredArticle] = {}
    for a in articles:
        key = a.cik or a.tickers[0]
        if key not in best or strength(a) > strength(best[key]):
            best[key] = a
    ranked = sorted(best.values(), key=strength, reverse=True)[:TOP_TICKERS]

    tone = _weighted([(a.sentiment_score, a.materiality / 3) for a in articles])
    unscored = inputs.unscored_count(engine, window_start, now)
    payload = {
        "window": {"start": window_start.isoformat(), "end": now.isoformat()},
        "tickers": [_article_brief(a) for a in ranked],
        "counts": {"material_articles": len(articles), "companies": len(best), "unscored": unscored},
        "insider_buys": inputs.insider_buys(engine, window_start - timedelta(hours=8))[:10],
        "earnings_today": inputs.earnings_on(engine, session_date),
        "macro_today": _econ_brief(inputs.econ_events_on(engine, session_date)),
        "cpi_surprise": inputs.cpi_surprises(engine, session_date)
        if any("Consumer Price Index" in e["title"] for e in inputs.econ_events_on(engine, session_date))
        else [],
        "premarket_moves": _market_moves(inputs.snapshot(engine, session_date, "premarket"), universe.context_symbols),
    }
    confidence = round(min(1.0, len(articles) / 20), 2) if tone is not None else 0.0
    return Signal(
        "premarket", session_date, now, tone and _clip(tone), confidence, _json(payload), inputs.freshness(engine)
    )
