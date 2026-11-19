"""Rebuild config/spx_universe.yaml: the top-N S&P 500 companies by market cap, with weights.

    uv run python scripts/refresh_spx_universe.py            # top 100 (default)
    uv run python scripts/refresh_spx_universe.py --top 50

Run after scripts/refresh_index_members.py, once per quarterly rebalance (March, June,
September, December). Candidates are every S&P 500 member in config/index_members.json, one per
company (share classes such as GOOGL/GOOG are grouped by SEC CIK).

Method:
  1. Rank all ~500 members by the market data provider's market cap (25 symbols per request).
     This pass only picks candidates: the top N plus a margin, and any member it has no cap for.
  2. For those candidates, compute the documented cap that sets the order and the weights:
       market cap = latest price (market data provider, e.g. Tradier quote)
                    × diluted weighted-average shares outstanding from the company's most recent
                      10-Q/10-K XBRL facts (SEC companyfacts API)
       weight     = market cap / sum of market caps of the selected companies, in percent

This approximates S&P's float-adjusted index weights; it is not the official weighting (S&P
publishes those under licence). Diluted share counts cover every share class, so multi-class
companies (Alphabet, Meta) count once. Companies that only tag per-class shares (Visa,
Berkshire) fall back to the 10-K's public float scaled by the price change since then.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

from eventalpha.config import Settings
from eventalpha.index_members import load_snapshot
from eventalpha.marketdata import create_market_data
from eventalpha.sec.client import RateLimitedClient
from eventalpha.signals.universe import tradier_symbol

MARGIN = 30  # extra provider-ranked candidates, so a company the SEC method ranks higher isn't cut


def group_by_company(symbols: list[str], universe: list[tuple[str, str, int | None]]) -> list[list[str]]:
    """One ticker list per company: share classes share a CIK. The primary (first) ticker is
    the one SEC ranks largest. `universe` rows are (ticker, cik, size_rank)."""
    cik_of = {t: c for t, c, _ in universe}
    rank = {t: r if r is not None else 10**9 for t, _, r in universe}
    groups: dict[str, list[str]] = {}
    for symbol in symbols:
        groups.setdefault(cik_of.get(symbol, f"?{symbol}"), []).append(symbol)
    return sorted((sorted(g, key=lambda t: (rank.get(t, 10**9), t)) for g in groups.values()), key=lambda g: g[0])


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
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--members", type=Path, default=Path("config/index_members.json"))
    parser.add_argument("--out", type=Path, default=Path("config/spx_universe.yaml"))
    args = parser.parse_args()

    s = Settings.from_env()
    engine = create_engine(s.database_url)
    with engine.connect() as conn:
        universe = [tuple(r) for r in conn.execute(text("SELECT ticker, cik, size_rank FROM ticker_universe")).all()]
        names = dict(conn.execute(text("SELECT cik, name FROM ticker_universe")).all())
    cik_of = {t: c for t, c, _ in universe}
    companies = group_by_company(list(load_snapshot(args.members).members["sp500"]), universe)
    unknown = [g[0] for g in companies if g[0] not in cik_of]
    companies = [g for g in companies if g[0] in cik_of]

    md = create_market_data(s)
    # Pass 1: cheap provider ranking, only to choose who gets the SEC-based cap.
    prelim = md.market_caps(sorted(tradier_symbol(g[0]) for g in companies))
    ranked = sorted(
        (g for g in companies if tradier_symbol(g[0]) in prelim), key=lambda g: -prelim[tradier_symbol(g[0])]
    )
    no_prelim = [g for g in companies if tradier_symbol(g[0]) not in prelim]
    candidates = ranked[: args.top + MARGIN] + no_prelim

    # Pass 2: the documented cap (price x SEC diluted shares) sets the order and weights.
    price_symbols = sorted({tradier_symbol(g[0]) for g in candidates})
    prices = {q.symbol: float(q.last) for q in md.quotes(price_symbols) if q.last}
    rows, skipped = [], list(unknown)
    with RateLimitedClient(s.sec_user_agent, s.sec_requests_per_second) as client:
        for tickers in candidates:
            cik, sym = cik_of[tickers[0]], tradier_symbol(tickers[0])
            got = market_cap(client, md, cik, sym, prices[sym]) if sym in prices else None
            if not got:
                skipped.append(tickers[0])
                continue
            cap, basis = got
            rows.append(
                {"tickers": tickers, "cik": cik, "name": names.get(cik, tickers[0]), "cap": cap, "basis": basis}
            )

    rows.sort(key=lambda r: -r["cap"])
    top = rows[: args.top]
    total = sum(r["cap"] for r in top)
    lines = [
        "# Top S&P 500 companies by market cap, used by the SPX overnight signal (candidates: every",
        "# S&P 500 member in config/index_members.json, share classes grouped by company).",
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
        lines.append(
            f'  - {{name: "{name}", cik: "{r["cik"]}", tickers: [{", ".join(r["tickers"])}], '
            f"weight: {weight:.2f}}}  # ${r['cap'] / 1e9:,.0f}B, {r['basis']}"
        )
    existing = args.out.read_text()
    context = existing[existing.index("# Market context") :] if "# Market context" in existing else ""
    args.out.write_text("\n".join(lines) + "\n\n" + context)
    print(
        f"wrote {args.out}: top {len(top)} of {len(rows)} priced candidates "
        f"({len(companies)} S&P 500 companies ranked); skipped {skipped or 'none'}"
    )
    for r in top[:10]:
        print(f"  {r['tickers'][0]:6} ${r['cap'] / 1e9:>8,.0f}B  {100 * r['cap'] / total:5.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
