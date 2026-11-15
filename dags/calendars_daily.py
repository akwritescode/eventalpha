"""
### Event calendars: economic releases and earnings dates

* **Economic:** BLS release calendar (exact ET times), FRED release dates for the non-BLS releases
  that matter (GDP, PCE, retail sales, claims, ...), and FOMC decisions from the Fed's calendar.
* **Earnings:** the market data provider's corporate calendar for the SPX top-50 plus every
  ticker that's been in the news in the last 30 days.
"""

from __future__ import annotations

from datetime import timedelta

from airflow.sdk import dag, task
from eventalpha_common import DEFAULT_ARGS, NY, START_DATE, engine, market_data, settings, table_asset, universe

LOOKAHEAD_DAYS = 45
LOOKBACK_DAYS = 30  # keep recent releases too: the web stream shows them with their actual values


@dag(schedule="0 6 * * 1-5", start_date=START_DATE, catchup=False, default_args=DEFAULT_ARGS,
     tags=["reference", "macro", "earnings"], doc_md=__doc__)
def calendars_daily():
    @task(outlets=[table_asset("econ_events")])
    def econ_calendar() -> int:
        import httpx
        import pendulum

        from eventalpha.calendars import FOMC_URL, bls_event_rows, fomc_event_rows, fred_event_rows
        from eventalpha.db import upsert_rows
        from eventalpha.macro.bls import BlsClient
        from eventalpha.macro.fred import FredClient

        today = pendulum.now(NY).date()
        start = today - timedelta(days=LOOKBACK_DAYS)
        end = today + timedelta(days=LOOKAHEAD_DAYS)
        s = settings()
        rows = bls_event_rows(BlsClient(s.bls_api_key, s.sec_user_agent).release_calendar(), start, end)
        rows += fred_event_rows(FredClient(s.fred_api_key).release_dates(start, end))
        fed = httpx.get(FOMC_URL, headers={"User-Agent": s.sec_user_agent}, timeout=30)
        fed.raise_for_status()
        rows += fomc_event_rows(fed.text, start, end)
        print(f"{len(rows)} economic events through {end}")
        return upsert_rows(engine(), "econ_events", rows, key=["source", "event_key"])

    @task(outlets=[table_asset("earnings_events")])
    def earnings_calendar() -> int:
        import pendulum
        from sqlalchemy import text

        from eventalpha.calendars import earnings_rows
        from eventalpha.db import upsert_rows
        from eventalpha.signals.universe import sec_ticker, tradier_symbol

        today = pendulum.now(NY).date()
        with engine().connect() as conn:
            news = conn.execute(text("""SELECT DISTINCT unnest(tickers) FROM articles
                                        WHERE published_at > now() - interval '30 days'""")).scalars().all()
        tickers = sorted({t for c in universe().companies for t in c.tickers} | set(news))
        provider = market_data()
        events = provider.earnings_events([tradier_symbol(t) for t in tickers], today,
                                          today + timedelta(days=LOOKAHEAD_DAYS))
        rows = earnings_rows(events, provider.name)
        for r in rows:  # store tickers the way SEC spells them, to join with articles
            r["ticker"] = sec_ticker(r["ticker"])
        print(f"{len(rows)} earnings dates for {len(tickers)} tickers")
        return upsert_rows(engine(), "earnings_events", rows, key=["ticker", "event_date"])

    econ_calendar()
    earnings_calendar()


calendars_daily()
