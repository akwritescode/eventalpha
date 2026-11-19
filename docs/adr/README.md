# Architecture decision records

Short records of decisions that shaped EventAlpha: the context, what was chosen, and what it
costs. A decision that's later reversed gets a new record that supersedes the old one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-airflow-runs-python-ingestion.md) | Airflow orchestrates ingestion written in Python, not a separate collector service | Accepted |
| [0002](0002-redis-streams-for-push.md) | Redis Streams carry events from the pipeline to the API, Telegram and browsers | Accepted |
| [0003](0003-vendor-neutral-classification.md) | Text classification sits behind a provider-neutral interface | Accepted |
| [0004](0004-official-data-sources-only.md) | Only official or licensed data sources, no scraping | Accepted |
| [0005](0005-web-ui-on-vercel.md) | The web UI is served by Vercel and calls the API directly | Accepted |
| [0006](0006-partitioned-minute-candles-and-s3-archives.md) | Daily minute-candle partitions with verified S3 archives and two-week hot retention | Accepted |

New record: copy the structure below into `NNNN-short-title.md`.

```markdown
# NNNN. Title

* Status: Proposed | Accepted | Superseded by NNNN
* Date: YYYY-MM-DD

## Context
## Decision
## Consequences
```
