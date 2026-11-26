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

## Amendment (2026-11-25): web search as a labelled last resort

When EventAlpha's own sources identify no catalyst, the web app can ask
`GET /api/v1/tickers/{ticker}/move-web-search`. Claude runs Anthropic's web search tool (a licensed
service, not scraping) and returns a short summary with citations. The answer is shown apart from
EventAlpha's evidence, labelled "From a web search · outside EventAlpha's sources", with titles and
links only, in line with the decision above. An answer without citations is discarded, replays never
search (later coverage would leak hindsight), and results are cached for a day and rate limited per IP.
Economic calendar entries and sector returns provide context and do not prevent this fallback.
