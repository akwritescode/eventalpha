INSERT INTO ticker_universe (ticker, cik, name) VALUES ('AAON', '824142', 'AAON, INC.');

INSERT INTO articles (id, source, source_id, form_type, url, title, company, cik, tickers, sec_items,
                      published_at, content_hash)
VALUES (1, 'sec_edgar', '0001628280-26-073758', '8-K', 'https://example.com/1', 'AAON 8-K: Results',
        'AAON, INC.', '824142', '{AAON}', '{2.02,9.01}', now() - interval '1 day', 'h1'),
       (2, 'sec_edgar', '0001628280-26-073759', '8-K', 'https://example.com/2', 'AAON 8-K: Guidance cut',
        'AAON, INC.', '824142', '{AAON}', '{7.01}', now() - interval '2 hours', 'h2'),
       (3, 'rss:federal_reserve', 'fed-1', NULL, 'https://example.com/3', 'Fed statement',
        NULL, NULL, '{}', '{}', now() - interval '3 hours', 'h3');

INSERT INTO article_scores (article_id, model, questions_version, sentiment, p_bullish, p_bearish, p_neutral,
                            sentiment_score, sentiment_confidence, materiality, materiality_confidence,
                            company_specific, events, input_tokens, scored_at)
VALUES (1, 'typesafe:jev-1.13.0', 'v1', 'neutral', 0.3, 0.2, 0.5, 0.1, 0.2, 1.0, 0.5, 0.9,
        '{"earnings_results": 0.9, "guidance_lowered": 0.1}', 100, now() - interval '20 hours'),
       -- a newer model re-scored article 1: the API must use this row
       (1, 'typesafe:jev-1.14.0', 'v1', 'bullish', 0.8, 0.1, 0.1, 0.7, 0.7, 2.0, 0.6, 0.95,
        '{"earnings_results": 0.97, "guidance_lowered": 0.02}', 100, now() - interval '10 hours'),
       (2, 'typesafe:jev-1.14.0', 'v1', 'bearish', 0.05, 0.9, 0.05, -0.85, 0.85, 3.0, 0.7, 0.97,
        '{"earnings_results": 0.1, "guidance_lowered": 0.95}', 100, now() - interval '1 hour');

INSERT INTO insider_transactions (accession, row_no, form_type, issuer_cik, ticker, issuer_name, owner_cik,
                                  owner_name, owner_count, is_director, is_officer, is_ten_percent_owner,
                                  officer_title, is_derivative, security_title, transaction_date,
                                  transaction_code, shares, price, acquired_disposed, shares_owned_after,
                                  ownership, filed_at)
VALUES ('0000000001-26-000001', 0, '4', '824142', 'AAON', 'AAON', '1', 'Jane CEO', 1, true, true, false, 'CEO',
        false, 'Common', current_date - 5, 'P', 1000, 50.00, 'A', 5000, 'D', now() - interval '4 days'),
       ('0000000001-26-000002', 0, '4', '824142', 'AAON', 'AAON', '2', 'Bob CFO', 1, false, true, false, 'CFO',
        false, 'Common', current_date - 3, 'S', 200, 55.00, 'D', 800, 'D', now() - interval '2 days'),
       ('0000000001-26-000003', 0, '4', '824142', 'AAON', 'AAON', '2', 'Bob CFO', 1, false, true, false, 'CFO',
        false, 'Common', current_date - 3, 'F', 50, 55.00, 'D', 750, 'D', now() - interval '2 days');

INSERT INTO sec_filings (accession, family, form_type, cik, company, date_filed, status, rows, detail)
VALUES ('0001628280-26-073758', 'events', '8-K', '824142', 'AAON, INC.', current_date - 1, 'loaded', 1, NULL),
       ('0001628280-26-000999', 'events', '8-K', '824142', 'AAON, INC.', current_date - 1, 'failed', 0, '503');

INSERT INTO signals (signal_type, session_date, generated_at, score, confidence, payload, inputs_as_of)
VALUES ('spx_overnight', current_date - 1, now() - interval '20 hours', 0.04, 0.4,
        '{"counts": {"company_specific": 369, "megacap_articles": 0}}', '{"articles_scored": "2026-11-14T20:14:00Z"}'),
       ('spx_overnight', current_date - 2, now() - interval '44 hours', -0.2, 0.5, '{}', '{}'),
       ('premarket', current_date - 1, now() - interval '27 hours', 0.3, 1.0, '{"tickers": []}', '{}');

INSERT INTO econ_events (source, event_key, title, event_date, scheduled_at, importance)
VALUES ('bls', 'cpi', 'Consumer Price Index', current_date + 3, now() + interval '3 days', 'high'),
       ('fred', 'gdp', 'Gross Domestic Product', current_date + 30, NULL, 'high');

INSERT INTO earnings_events (ticker, event_date, description, status, fiscal_year, market_cap, source)
VALUES ('NVDA', current_date + 2, 'NVIDIA Q3 Earnings Result', 'Confirmed', 2027, 4.5e12, 'tradier'),
       ('AAA', current_date + 2, 'AAA Q3 Earnings Result', 'Estimated', 2026, 1.2e8, 'tradier');

INSERT INTO inflation_nowcasts (horizon, target_period, measure, vintage, value, actual)
VALUES ('mom', '2026-11', 'cpi', current_date - 2, 0.12, NULL),
       ('mom', '2026-11', 'cpi', current_date - 1, 0.135, NULL),
       ('mom', '2026-10', 'cpi', current_date - 30, 0.242, 0.35);

-- A CPI release two days ago for the prior month: BLS SA index up 0.30%, nowcast said 0.20%.
INSERT INTO econ_events (source, event_key, title, event_date, scheduled_at, importance)
VALUES ('bls', 'cpi-past', 'Consumer Price Index', current_date - 2,
        ((current_date - 2) + time '08:30') AT TIME ZONE 'America/New_York', 'high');
INSERT INTO macro_observations (source, series_id, period, value, preliminary)
VALUES ('bls', 'CUSR0000SA0', (date_trunc('month', current_date - 2) - interval '1 month')::date, 300.900, false),
       ('bls', 'CUSR0000SA0', (date_trunc('month', current_date - 2) - interval '2 month')::date, 300.000, false),
       ('bls', 'CUSR0000SA0', (date_trunc('month', current_date - 2) - interval '3 month')::date, 299.400, false);
INSERT INTO inflation_nowcasts (horizon, target_period, measure, vintage, value, actual)
VALUES ('mom', to_char(date_trunc('month', current_date - 2) - interval '1 month', 'YYYY-MM'), 'cpi', current_date - 3, 0.20, NULL);

UPDATE signals SET message = '<b>SPX overnight</b>
neutral +0.04' WHERE signal_type = 'spx_overnight' AND session_date = current_date - 1;

-- Explicit fixture IDs above bypass the default sequence.
SELECT setval(pg_get_serial_sequence('articles', 'id'), max(id)) FROM articles;
