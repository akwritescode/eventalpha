-- Local demo only. The filing and acceptance time are real. X IDs and observation times are synthetic.
-- Load through make seed after migrations. Do not load on a live warehouse.

INSERT INTO articles (source, source_id, form_type, url, title, tickers, published_at, ingested_at,
                      updated_at, content_hash)
VALUES ('sec_edgar', 'demo-move-0001045810-25-000082', '8-K',
        'https://www.sec.gov/Archives/edgar/data/1045810/000104581025000082/nvda-20250409.htm',
        'NVIDIA 8-K on H20 export licensing and expected charges', '{NVDA}',
        '2025-04-15 17:22:59-04', '2025-04-15 17:26:00-04', '2025-04-15 17:26:00-04', 'demo-move')
ON CONFLICT (source, source_id) DO NOTHING;

INSERT INTO x_leads (post_id, ticker, paraphrase, published_at, first_seen_at, article_id,
                     article_content_hash, verified_at)
SELECT v.post_id, 'NVDA', v.paraphrase, v.published_at, v.first_seen_at,
       CASE WHEN v.verified_at IS NOT NULL THEN a.id END,
       CASE WHEN v.verified_at IS NOT NULL THEN a.content_hash END,
       v.verified_at
FROM articles a
CROSS JOIN (VALUES
  ('99000000000000000001',
   'NVIDIA disclosed new H20 export licensing requirements and expected charges of up to about $5.5 billion.',
   '2025-04-15 17:23:00-04'::timestamptz, '2025-04-15 17:25:00-04'::timestamptz,
   '2025-04-15 17:27:00-04'::timestamptz),
  ('99000000000000000002', 'A second post flagged the H20 export license requirement disclosed in the 8-K.',
   '2025-04-15 17:29:00-04', '2025-04-15 17:37:00-04', '2025-04-15 17:38:00-04'),
  ('99000000000000000003', 'A later post speculated about cancellations of H20 orders.',
   '2025-04-15 17:40:00-04', '2025-04-15 17:41:00-04', NULL)
) AS v(post_id, paraphrase, published_at, first_seen_at, verified_at)
WHERE a.source = 'sec_edgar' AND a.source_id = 'demo-move-0001045810-25-000082'
ON CONFLICT (post_id) DO NOTHING;
