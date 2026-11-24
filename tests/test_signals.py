"""Signal scoring with the warehouse reads replaced by fixed inputs: the arithmetic, the
filters and the confidence rules, independent of Postgres."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from eventalpha.signals import build, inputs
from eventalpha.signals.universe import Company, Universe

NOW = datetime(2026, 11, 13, 21, 45, tzinfo=UTC)
START = datetime(2026, 11, 12, 21, 0, tzinfo=UTC)
UNIVERSE = Universe(
    as_of="2026-11-14",
    companies=(Company("NVIDIA", "1045810", ("NVDA",), 7.5), Company("Apple", "320193", ("AAPL",), 6.5)),
    context_symbols={},
)


def scored(id_: int, cik: str | None, tickers: list[str], score: float, materiality: float, specific: float = 0.95):
    return inputs.ScoredArticle(
        id=id_,
        title=f"Item {id_}",
        url=f"https://example.com/{id_}",
        source="sec_edgar",
        form_type="8-K",
        cik=cik,
        tickers=tickers,
        published_at=NOW,
        sentiment="bullish" if score > 0 else "bearish",
        sentiment_score=score,
        materiality=materiality,
        company_specific=specific,
    )


@pytest.fixture
def warehouse(monkeypatch):
    """Patch every warehouse read; tests set `articles` and `unscored`."""
    state = {"articles": [], "unscored": 0}
    monkeypatch.setattr(inputs, "scored_articles", lambda e, s, n: state["articles"])
    monkeypatch.setattr(inputs, "unscored_count", lambda e, s, n: state["unscored"])
    for name in ("econ_events_on", "earnings_on", "insider_buys", "cpi_surprises", "latest_nowcast"):
        monkeypatch.setattr(inputs, name, lambda *a, **k: [])
    monkeypatch.setattr(inputs, "snapshot", lambda *a, **k: {})
    monkeypatch.setattr(inputs, "freshness", lambda e: {})
    return state


def test_weighted_mean_clip_and_json_helpers():
    assert build._weighted([(1.0, 1.0), (-1.0, 3.0)]) == -0.5
    assert build._weighted([(1.0, 0.0)]) is None
    assert build._clip(1.7) == 1.0 and build._clip(-3) == -1.0
    assert build._json({"d": date(2026, 11, 13), "x": [Decimal("1.5")]}) == {"d": "2026-11-13", "x": [1.5]}


def test_overnight_blends_megacap_and_breadth_news(warehouse):
    warehouse["articles"] = [
        scored(1, "1045810", ["NVDA"], 0.8, 3.0),  # top-100 company
        scored(2, None, ["SMOL"], -0.4, 1.5),  # breadth only
        scored(3, None, ["NOISE"], 0.9, 3.0, specific=0.2),  # not company-specific: ignored
    ]
    sig = build.build_spx_overnight(None, UNIVERSE, date(2026, 11, 13), START, NOW, None)
    mega = 0.8  # one megacap article
    breadth = (0.8 * 1.0 + -0.4 * 0.5) / 1.5  # materiality/3 weights
    assert sig.score == pytest.approx(0.6 * mega + 0.4 * breadth)
    assert sig.payload["counts"] == {"articles_scored": 3, "company_specific": 2, "megacap_articles": 1, "unscored": 0}
    assert sig.payload["universe_size"] == len(UNIVERSE.companies)
    # Confidence = coverage × (0.4 × breadth coverage + 0.6 × megacap coverage).
    assert sig.confidence == round(1.0 * (0.4 * 2 / 40 + 0.6 * 1 / 5), 2)


def test_overnight_without_news_has_no_score_and_no_confidence(warehouse):
    warehouse["unscored"] = 12
    sig = build.build_spx_overnight(None, UNIVERSE, date(2026, 11, 13), START, NOW, None)
    assert sig.score is None and sig.confidence == 0.0


def test_premarket_keeps_material_company_news_and_ranks_one_item_per_company(warehouse):
    warehouse["articles"] = [
        scored(1, "1045810", ["NVDA"], 0.5, 2.0),
        scored(2, "1045810", ["NVDA"], -0.9, 3.0),  # NVDA's strongest item wins the ranking slot
        scored(3, None, ["AAPL"], 0.6, 1.0),  # below MIN_MATERIALITY: dropped
        scored(4, None, [], 0.9, 3.0),  # no ticker: dropped
    ]
    sig = build.build_premarket(None, UNIVERSE, date(2026, 11, 13), START, NOW)
    assert [t["title"] for t in sig.payload["tickers"]] == ["Item 2"]
    assert sig.payload["counts"]["material_articles"] == 2
    assert sig.score == pytest.approx((0.5 * 2 / 3 + -0.9 * 3 / 3) / (2 / 3 + 1))
    assert sig.confidence == 0.1
