# 0004. Only official or licensed data sources, no scraping

* Status: Accepted
* Date: 2026-11-14

## Context

Useful market data (options positioning, consensus forecasts, curated news) is often only
available by scraping sites whose terms forbid it. EventAlpha is public, so whatever it does
is visible and reproducible by anyone.

## Decision

Use official or licensed sources only: SEC EDGAR, BLS, FRED, the Federal Reserve, the
Cleveland Fed's inflation nowcast (non-commercial, with attribution), Tradier's market data
API, and press-release RSS feeds that publishers syndicate. No scraping of sites that
prohibit it, and no republishing of third-party content beyond titles, summaries and links.

## Consequences

* Anyone can run the project without breaking terms of service.
* No consensus economic forecasts: the CPI surprise is measured against the Cleveland Fed
  nowcast instead.
* News coverage is narrower than a commercial feed; tickers in press releases are inferred
  from company names when the feed omits the exchange citation.
