# 0006. Partition minute candles by day and verify S3 archives before reclamation

* Status: Accepted
* Date: 2026-11-18

## Context

Move explanations need the selected stock and benchmarks over the same intraday window.
The Nasdaq-100 and S&P 500 together cover hundreds of symbols, so collecting every minute
creates roughly 200,000 rows per regular session. Keeping this history indefinitely in
Postgres would make storage grow with every trading day.

The interactive read path focuses on the previous seven days. Candle observation times must
survive retries and archival so a replay can enforce when EventAlpha first collected a value.
Daily candles also serve longer-running research and signal calculations.

## Decision

Collect the union of Nasdaq's published Nasdaq-100 constituent list and State Street's SPY
equity holdings, used as the S&P 500 membership proxy. Include every listed share class,
deduplicate symbols, and add SPY, QQQ and SMH. Use a reviewed checked-in snapshot without
automated publisher requests. Keep this universe separate from the weighted
top-50 universe used by the existing SPX signal.

Use the existing market-data provider boundary and Airflow ingestion pipeline. Two mapped
workers each process batches of 25 symbols with at least 1.5 seconds per symbol request cycle.
New symbols receive eight calendar days of history. Later requests overlap one hour.
Preserve the first collected prices and their first-seen time on natural-key conflicts.

Store minute OHLCV in daily UTC range partitions of `price_bars_minute`, keyed by
`(symbol, started_at)`. Create partitions ahead of collection. Keep the current UTC date
and the preceding fourteen dates in Postgres. Complete days become eligible for archival
when their date precedes the current UTC date minus fourteen days.

Use an export, verify, then drop sequence. EventAlpha
uses gzip JSONL, extending its existing JSONL conventions without a new encoding dependency.
Each archive includes first-seen times and a manifest. Download the uploaded object and verify
its SHA-256 digest, row count, and UTC day. Write and read back the manifest before dropping
the corresponding partition. Reclaiming a whole partition releases its storage files.

Use `MINUTE_ARCHIVE_BUCKET`, falling back to the existing `RAW_BUCKET`. The default prefix is
`minute_bars`. A local deployment sharing the production bucket uses `minute_bars/local`
so each environment owns its manifests. Keep credentials in environment configuration.

## Consequences

* Recent explanation requests read Postgres directly. The two-week hot window covers the
  seven-day interactive lookback and leaves time to recover missed collection.
* Daily candles remain in `price_bars_daily`, outside the minute archive and retention code.
* Missing bucket settings or failed archive verification retain the affected Postgres data.
  An unavailable archive can therefore cause local storage to grow until it is repaired.
* Partition locks protect export and the final SQL snapshot comparison. Network transfers run
  outside transactions. The nightly task bounds lock acquisition to five seconds.
* The default partition is a backstop for unexpected loads. Nonempty default partitions
  stop archival outside the collector range. Archival creates dated partitions for all default dates and moves
  overlapping rows atomically.
* SPY holdings are a membership proxy. The stored source and fetch time make the chosen
  universe inspectable. Current membership does not reconstruct historical index membership.
* Cold archives support offline research. Restoring them is a separate operation from the
  current interactive API.

Implementation and operating details are in [Intraday data design](../INTRADAY_DATA_DESIGN.md).

### Pre-merge revisions

Constituent selection is snapshot-only, with reviewed updates, until automated publisher access
has been established. Archive transfers run outside database locks. A final locked row-count/newest-observation
comparison rejects inserts before reclamation. Default-partition rows are moved atomically
when their dated partition is created. See the intraday data design for recovery and timing.
