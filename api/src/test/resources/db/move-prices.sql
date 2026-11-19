WITH filing AS (
    INSERT INTO articles (source, source_id, form_type, url, title, tickers, published_at, ingested_at,
                          updated_at, content_hash)
    VALUES ('sec_edgar', 'test-intraday-filing', '8-K', 'https://www.sec.gov/example',
            'NVDA 8-K: Guidance update', '{NVDA}', '2025-06-10 10:30-04', '2025-06-10 10:31-04',
            '2025-06-10 10:31-04', 'test-intraday')
    RETURNING id
)
INSERT INTO article_scores (article_id, model, questions_version, sentiment, p_bullish, p_bearish, p_neutral,
                            sentiment_score, sentiment_confidence, materiality, materiality_confidence,
                            company_specific, events, scored_at)
SELECT id, 'test:jev', 'v1', 'bearish', 0.05, 0.90, 0.05, -0.85, 0.90, 2.8, 0.90, 0.95,
       '{"guidance_lowered": 0.92}', '2025-06-10 10:45-04' FROM filing;

INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
VALUES ('NVDA', '2025-06-10 10:24-04', 100, 100.5, '2025-06-10 10:29-04'),
       ('NVDA', '2025-06-10 10:38-04', 98, 97.5, '2025-06-10 10:42-04'),
       ('NVDA', '2025-06-10 10:39-04', 97.5, 120, '2025-06-10 10:42-04'),
       ('SPY', '2025-06-10 10:24-04', 500, 500.5, '2025-06-10 10:29-04'),
       ('SPY', '2025-06-10 10:38-04', 499.5, 499, '2025-06-10 10:42-04'),
       ('SMH', '2025-06-10 10:24-04', 200, 200.5, '2025-06-10 10:29-04'),
       ('SMH', '2025-06-10 10:38-04', 199.5, 198, '2025-06-10 10:42-04');

INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
VALUES ('NVDA', '2025-06-10 10:23-04', 100, 100, '2025-06-10 10:29-04'),
       ('SPY', '2025-06-10 10:23-04', 500, 500, '2025-06-10 10:29-04'),
       ('SMH', '2025-06-10 10:23-04', 200, 200, '2025-06-10 10:29-04');
