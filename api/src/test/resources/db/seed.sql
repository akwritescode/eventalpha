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
VALUES (1, 'jev-1.13.0', 'v1', 'neutral', 0.3, 0.2, 0.5, 0.1, 0.2, 1.0, 0.5, 0.9,
        '{"earnings_results": 0.9, "guidance_lowered": 0.1}', 100, now() - interval '20 hours'),
       -- a newer model re-scored article 1: the API must use this row
       (1, 'jev-1.14.0', 'v1', 'bullish', 0.8, 0.1, 0.1, 0.7, 0.7, 2.0, 0.6, 0.95,
        '{"earnings_results": 0.97, "guidance_lowered": 0.02}', 100, now() - interval '10 hours'),
       (2, 'jev-1.14.0', 'v1', 'bearish', 0.05, 0.9, 0.05, -0.85, 0.85, 3.0, 0.7, 0.97,
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
