# 0001. Airflow orchestrates ingestion written in Python

* Status: Accepted
* Date: 2026-11-14

## Context

Ingestion is I/O-bound HTTP work against rate-limited sources (SEC EDGAR allows 10 requests
per second), on schedules tied to the New York trading day, with backfills for past filing
dates. A separate long-running collector service (for example in Go) was considered for the
fetching, with Airflow only scheduling downstream work.

## Decision

Fetching runs inside Airflow tasks, in Python. Business logic lives in the `eventalpha`
package; DAG files only wire it together.

## Consequences

* Retries, backfills (`airflow backfill create`), dynamic task mapping per feed, pools with
  priorities, data-aware scheduling through assets and run history come from one tool.
* One language and one deployable for the whole pipeline; the code is testable without Airflow.
* Per-task overhead (process start, DAG parse) is higher than a resident collector. That's
  acceptable at minutes-level freshness; sub-second ingestion would need a streaming collector.
