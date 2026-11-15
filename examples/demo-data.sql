-- Demo data for a fresh clone: fills every panel of the web UI without API keys or a day of
-- ingestion. Load with `make seed` (the stack must be up and the warehouse migrated).
--
-- * Refuses to run on a warehouse that already has articles: it's for empty databases only.
-- * Dates are relative to now(), so the demo always looks current.
-- * Every row is marked "demo" (source_id/accession/event_key prefix, model "demo:model");
--   examples/README.md shows how to remove it again.
-- * Titles are invented; URLs point to example.com. Not real filings, not investment advice.

\set ON_ERROR_STOP on
BEGIN;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM articles) THEN
    RAISE EXCEPTION 'the warehouse already has articles: demo data is only for an empty database';
  END IF;
END $$;

INSERT INTO ticker_universe (ticker, cik, name, size_rank) VALUES
  ('DEMOA', '9000001', 'Demo Analytics Inc', 120),
  ('DEMOB', '9000002', 'Demo Biotech Corp', 900),
  ('DEMOC', '9000003', 'Demo Cloud Holdings', 60)
ON CONFLICT (ticker) DO NOTHING;

-- Articles and their classification, joined on source_id (ids come from the sequence).
WITH demo (source_id, source, form_type, title, summary, company, cik, tickers, sec_items, hours_ago,
           sentiment, p_bull, p_bear, materiality, company_specific, events) AS (
  VALUES
  ('demo-8k-1', 'sec_edgar', '8-K', 'Demo Cloud Holdings 8-K: Results of Operations and Financial Condition',
   'Quarterly revenue up 31% year over year; full-year guidance raised.', 'DEMO CLOUD HOLDINGS', '9000003',
   '{DEMOC}'::varchar[], '{2.02,9.01}'::varchar[], 2, 'bullish', 0.86, 0.04, 2.8, 0.97,
   '{"earnings_results": 0.96, "guidance_raised": 0.91}'),
  ('demo-8k-2', 'sec_edgar', '8-K', 'Demo Biotech Corp 8-K: Departure of Directors or Certain Officers',
   'Chief medical officer resigns effective immediately.', 'DEMO BIOTECH CORP', '9000002',
   '{DEMOB}', '{5.02}', 5, 'bearish', 0.08, 0.71, 2.1, 0.95, '{"executive_change": 0.94}'),
  ('demo-8k-3', 'sec_edgar', '8-K', 'Demo Analytics Inc 8-K: Entry into a Material Definitive Agreement',
   'Agreement to acquire a data-integration startup for $420 million in cash.', 'DEMO ANALYTICS INC', '9000001',
   '{DEMOA}', '{1.01,8.01}', 9, 'bullish', 0.64, 0.10, 2.6, 0.96, '{"m_and_a": 0.93}'),
  ('demo-10q-1', 'sec_edgar', '10-Q', 'Demo Analytics Inc 10-Q: Quarterly report',
   'Revenue and margins in line; liquidity unchanged.', 'DEMO ANALYTICS INC', '9000001',
   '{DEMOA}', '{}', 30, 'neutral', 0.30, 0.15, 1.2, 0.9, '{"earnings_results": 0.72}'),
  ('demo-news-1', 'rss:prnewswire_all', NULL, 'Demo Biotech announces Phase 3 trial meets primary endpoint',
   'Late-stage study of the lead candidate showed a statistically significant improvement.', NULL, NULL,
   '{DEMOB}', '{}', 3, 'bullish', 0.82, 0.06, 2.9, 0.98, '{"clinical_trial_results": 0.95}'),
  ('demo-news-2', 'rss:prnewswire_earnings', NULL, 'Demo Cloud Holdings to report fourth-quarter results',
   'Conference call scheduled after the market close.', NULL, NULL,
   '{DEMOC}', '{}', 20, 'neutral', 0.20, 0.05, 0.6, 0.9, '{"earnings_date": 0.88}'),
  ('demo-news-3', 'rss:federal_reserve', NULL, 'Federal Reserve Board announces approval of a bank merger application',
   'Approval of an application by two regional bank holding companies.', NULL, NULL,
   '{}', '{}', 26, 'neutral', 0.25, 0.10, 0.8, 0.4, '{}')
), inserted AS (
  INSERT INTO articles (source, source_id, form_type, url, title, summary, company, cik, tickers, sec_items,
                        published_at, content_hash)
  SELECT source, source_id, form_type, 'https://example.com/' || source_id, title, summary, company, cik, tickers,
         sec_items, now() - make_interval(hours => hours_ago), md5(source_id)
  FROM demo
  RETURNING id, source_id
)
INSERT INTO article_scores (article_id, model, questions_version, sentiment, p_bullish, p_bearish, p_neutral,
                            sentiment_score, sentiment_confidence, materiality, materiality_confidence,
                            company_specific, events, input_tokens, scored_at)
SELECT i.id, 'demo:model', 'v1', d.sentiment, d.p_bull, d.p_bear, 1 - d.p_bull - d.p_bear, d.p_bull - d.p_bear,
       0.8, d.materiality, 0.7, d.company_specific, d.events::jsonb, 0, now()
FROM inserted i JOIN demo d USING (source_id);

-- Two directors buying the same stock within 30 days: an insider cluster.
INSERT INTO insider_transactions (accession, row_no, form_type, issuer_cik, ticker, issuer_name, owner_cik,
                                  owner_name, owner_count, is_director, is_officer, is_ten_percent_owner,
                                  officer_title, is_derivative, security_title, transaction_date,
                                  transaction_code, shares, price, acquired_disposed, shares_owned_after,
                                  ownership, filed_at)
VALUES ('demo-form4-1', 0, '4', '9000001', 'DEMOA', 'Demo Analytics Inc', '1', 'Alex Director', 1, true, false,
        false, NULL, false, 'Common', current_date - 4, 'P', 20000, 42.10, 'A', 120000, 'D', now() - interval '3 days'),
       ('demo-form4-2', 0, '4', '9000001', 'DEMOA', 'Demo Analytics Inc', '2', 'Sam Director', 1, true, false,
        false, NULL, false, 'Common', current_date - 2, 'P', 8000, 43.50, 'A', 30000, 'D', now() - interval '1 day');

-- A released CPI print (actual vs. the nowcast) and what's coming up.
INSERT INTO econ_events (source, event_key, title, event_date, scheduled_at, importance) VALUES
  ('bls', 'demo-cpi-past', 'Consumer Price Index', current_date - 2,
   ((current_date - 2) + time '08:30') AT TIME ZONE 'America/New_York', 'high'),
  ('bls', 'demo-ppi-next', 'Producer Price Index', current_date + 2,
   ((current_date + 2) + time '08:30') AT TIME ZONE 'America/New_York', 'high'),
  ('fred', 'demo-retail-next', 'Advance Monthly Sales for Retail and Food Services', current_date + 3, NULL, 'high');
INSERT INTO macro_observations (source, series_id, period, value, preliminary) VALUES
  ('bls', 'CUSR0000SA0', (date_trunc('month', current_date - 2) - interval '1 month')::date, 300.900, false),
  ('bls', 'CUSR0000SA0', (date_trunc('month', current_date - 2) - interval '2 month')::date, 300.000, false),
  ('bls', 'CUSR0000SA0', (date_trunc('month', current_date - 2) - interval '3 month')::date, 299.400, false)
ON CONFLICT DO NOTHING;
INSERT INTO inflation_nowcasts (horizon, target_period, measure, vintage, value, actual) VALUES
  ('mom', to_char(date_trunc('month', current_date - 2) - interval '1 month', 'YYYY-MM'), 'cpi', current_date - 3, 0.20, 0.30),
  ('mom', to_char(current_date, 'YYYY-MM'), 'cpi', current_date - 1, 0.18, NULL)
ON CONFLICT DO NOTHING;

INSERT INTO earnings_events (ticker, event_date, description, status, fiscal_year, market_cap, source) VALUES
  ('DEMOC', current_date + 1, 'Demo Cloud Holdings Q4 Earnings Result', 'Confirmed', 2026, 9.1e10, 'demo'),
  ('DEMOA', current_date + 1, 'Demo Analytics Q4 Earnings Result', 'Estimated', 2026, 1.4e10, 'demo'),
  ('DEMOB', current_date + 4, 'Demo Biotech Q4 Earnings Result', 'Confirmed', 2026, 2.2e9, 'demo')
ON CONFLICT DO NOTHING;

INSERT INTO signals (signal_type, session_date, generated_at, score, confidence, payload, inputs_as_of, message)
VALUES ('premarket', current_date, now() - interval '1 hour', 0.42, 0.6,
        '{"tickers": [{"tickers": ["DEMOB"], "title": "Demo Biotech announces Phase 3 trial meets primary endpoint",
          "url": "https://example.com/demo-news-1", "sentiment": "bullish", "sentiment_score": 0.76,
          "materiality": 2.9}], "counts": {"material_articles": 3, "companies": 3, "unscored": 0}}',
        '{}', '<b>Premarket</b> (demo)
bullish +0.42 · confidence 60%
DEMOB: Phase 3 trial meets primary endpoint'),
       ('spx_overnight', current_date - 1, now() - interval '16 hours', 0.12, 0.45,
        '{"components": {"megacap_news": 0.2, "breadth": 0.05}, "counts": {"company_specific": 6, "megacap_articles": 1}}',
        '{}', '<b>SPX overnight</b> (demo)
mildly bullish +0.12 · confidence 45%');

COMMIT;
