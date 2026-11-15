"""Rebuild config/spx_universe.yaml: the top-N S&P 500 companies by market cap, with weights.

    uv run python scripts/refresh_spx_universe.py            # top 50 (default)
    uv run python scripts/refresh_spx_universe.py --top 25

Method (re-run quarterly, after the March/June/September/December index rebalances):
  market cap = latest price (market data provider, e.g. Tradier quote)
               × diluted weighted-average shares outstanding from the company's most recent
                 10-Q/10-K XBRL facts (SEC companyfacts API, us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding)
  weight     = market cap / sum of market caps of the selected companies, in percent

This approximates S&P's float-adjusted index weights; it is not the official weighting (S&P
publishes those under licence). Diluted share counts cover every share class, so multi-class
companies (Alphabet, Meta) count once; Berkshire reports in Class A equivalents, so it's priced
with BRK.A. CANDIDATES is a hand-kept superset of the largest US companies; the script ranks
them on real data and keeps the top N.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

from eventalpha.config import Settings
from eventalpha.marketdata import create_market_data
from eventalpha.sec.client import RateLimitedClient
from eventalpha.signals.universe import tradier_symbol

# (SEC ticker(s), price ticker if different). First ticker is the company's primary one.
CANDIDATES: list[tuple[list[str], str | None]] = [
    (["NVDA"], None), (["AAPL"], None), (["MSFT"], None), (["AMZN"], None), (["GOOGL", "GOOG"], None),
    (["META"], None), (["AVGO"], None), (["TSLA"], None), (["BRK-B"], None), (["JPM"], None),
    (["LLY"], None), (["V"], None), (["WMT"], None), (["ORCL"], None), (["NFLX"], None), (["XOM"], None),
    (["MA"], None), (["COST"], None), (["JNJ"], None), (["PLTR"], None), (["HD"], None), (["ABBV"], None),
    (["BAC"], None), (["AMD"], None), (["PG"], None), (["UNH"], None), (["KO"], None), (["CVX"], None),
    (["CSCO"], None), (["GE"], None), (["WFC"], None), (["CRM"], None), (["IBM"], None), (["PM"], None),
    (["MS"], None), (["ABT"], None), (["GS"], None), (["LIN"], None), (["MCD"], None), (["INTU"], None),
    (["MU"], None), (["AXP"], None), (["NOW"], None), (["T"], None), (["TMO"], None), (["MRK"], None),
    (["DIS"], None), (["ISRG"], None), (["RTX"], None), (["PEP"], None), (["CAT"], None), (["BX"], None),
    (["QCOM"], None), (["UBER"], None), (["BKNG"], None), (["VZ"], None), (["AMAT"], None), (["TXN"], None),
    (["SCHW"], None), (["BLK"], None), (["C"], None), (["SPGI"], None), (["ANET"], None), (["LRCX"], None),
    (["NEE"], None), (["PGR"], None), (["APP"], None), (["KLAC"], None), (["ADBE"], None), (["GEV"], None),
]
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
SHARE_TAGS = ("WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic")
STALE_BEFORE = "2025-01-01"  # older share counts are ignored (some filers stopped tagging them)


def _latest(values: list[dict]) -> dict | None:
    recent = [v for v in values if v.get("form") in ("10-Q", "10-K") and v.get("val") and v["end"] >= STALE_BEFORE]
    return max(recent, key=lambda v: (v["end"], v.get("filed", ""))) if recent else None


def market_cap(client: RateLimitedClient, md, cik: str, price_symbol: str, price: float) -> tuple[float, str] | None:
    """(market cap in $, basis). Share counts first; companies that only tag per-class shares
    (which companyfacts omits) fall back to the 10-K's public float scaled by the price change."""
    resp = client.get(FACTS_URL.format(cik=cik))
    if resp.status_code != 200:
        return None
    facts = resp.json().get("facts", {})
    for tag in SHARE_TAGS:
        v = _latest(facts.get("us-gaap", {}).get(tag, {}).get("units", {}).get("shares", []))
        if v:
            kind = "diluted" if "Diluted" in tag else "basic"
            return float(v["val"]) * price, f"{kind} shares as of {v['end']}"
    floats = facts.get("dei", {}).get("EntityPublicFloat", {}).get("units", {}).get("USD", [])
    if floats:
        f = max(floats, key=lambda v: (v["end"], v.get("filed", "")))
        end = date.fromisoformat(f["end"])
        bars = md.daily_bars(price_symbol, end - timedelta(days=7), end)
        if bars:
            then = float(bars[-1].close)
            return float(f["val"]) * price / then, f"public float as of {f['end']} scaled by price"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("config/spx_universe.yaml"))
    args = parser.parse_args()

    s = Settings.from_env()
    engine = create_engine(s.database_url)
    with engine.connect() as conn:
        cik_of = dict(conn.execute(text("SELECT ticker, cik FROM ticker_universe")).all())
        names = dict(conn.execute(text("SELECT cik, name FROM ticker_universe")).all())

    md = create_market_data(s)
    price_symbols = {c[1] or tradier_symbol(c[0][0]) for c in CANDIDATES}
    prices = {q.symbol: float(q.last) for q in md.quotes(sorted(price_symbols)) if q.last}

    rows, skipped = [], []
    with RateLimitedClient(s.sec_user_agent, s.sec_requests_per_second) as client:
        for tickers, price_ticker in CANDIDATES:
            cik = cik_of.get(tickers[0])
            sym = price_ticker or tradier_symbol(tickers[0])
            got = market_cap(client, md, cik, sym, prices[sym]) if cik and sym in prices else None
            if not got:
                skipped.append(tickers[0])
                continue
            cap, basis = got
            name = names.get(cik, tickers[0])
            rows.append({"tickers": tickers, "cik": cik, "name": name, "cap": cap, "basis": basis})

    rows.sort(key=lambda r: -r["cap"])
    top = rows[: args.top]
    total = sum(r["cap"] for r in top)
    lines = [
        "# Top S&P 500 companies by market cap, used by the SPX overnight signal.",
        f"# Generated {date.today().isoformat()} by scripts/refresh_spx_universe.py (re-run quarterly).",
        "#",
        "# weight = this company's market cap as a % of the listed companies' combined cap, where",
        "#   market cap = latest price (Tradier quote) x weighted-average diluted (else basic) shares",
        "#   outstanding from the company's most recent 10-Q/10-K XBRL facts (SEC companyfacts API).",
        "#   Companies that only tag shares per class (omitted by companyfacts: Visa, Berkshire) use",
        "#   the public float from their latest 10-K cover, scaled by the price change since then.",
        "# An approximation of S&P's float-adjusted weights, not the official (licensed) index weights.",
        "# Multi-class companies count once (share counts cover all classes).",
        "# Tickers are spelled as in SEC's ticker list (BRK-B).",
        f'as_of: "{date.today().isoformat()}"',
        f"weight_basis: share of top-{len(top)} market cap (%)",
        "companies:",
    ]
    for r in top:
        name = r["name"].replace('"', "'")
        weight = 100 * r["cap"] / total
        lines.append(f'  - {{name: "{name}", cik: "{r["cik"]}", tickers: [{", ".join(r["tickers"])}], '
                     f'weight: {weight:.2f}}}  # ${r["cap"] / 1e9:,.0f}B, {r["basis"]}')
    existing = args.out.read_text()
    context = existing[existing.index("# Market context"):] if "# Market context" in existing else ""
    args.out.write_text("\n".join(lines) + "\n\n" + context)
    print(f"wrote {args.out}: top {len(top)} of {len(rows)} priced candidates; skipped {skipped or 'none'}")
    for r in top[:10]:
        print(f"  {r['tickers'][0]:6} ${r['cap'] / 1e9:>8,.0f}B  {100 * r['cap'] / total:5.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
