# EventAlpha architecture

How the pieces fit together, what each part of the repo does, and why it's built this way.
For setup commands see the [README](../README.md); diagrams of the data moving through the
system are in [DATA_FLOW.md](DATA_FLOW.md); requirements, scale and failure modes are in
[SYSTEM_DESIGN.md](SYSTEM_DESIGN.md); production is in [DEPLOY.md](DEPLOY.md).

## The big picture

```
 Sources                     Orchestration (Airflow 3)                         Storage / serving
 ───────                     ─────────────────────────                         ─────────────────
 SEC EDGAR ──► sec_events_daily    8-K, 6-K, 13D, S-1, 424B ──┐
           ──► sec_insider_daily   Form 4                     │
           ──► sec_holdings_daily  13F-HR                     ├──► PostgreSQL 18 warehouse
           ──► sec_periodic_daily  10-K / 10-Q + XBRL facts   │      (schema owned by Alembic)
 RSS feeds ──► rss_news_hourly                                │             │
                                                              │             │ read-only
               asset "articles" updated ──► classify_articles │             ▼
                                   (pluggable classifier) ────┘      Spring Boot API :8081
                                                                       /api/v1/...  /docs
 every fetch ──► raw landing zone (JSONL, local disk or bucket)

 high-impact scores ──XADD──► Redis Stream "eventalpha:events" ──► API SSE  /api/v1/stream/events
                                                              └──► consumer group "telegram" ──► alert bot
```

Two kinds of data come out of SEC filings:

* **Text events** (8-K, 6-K, Schedule 13D, offerings) and RSS items become `articles`,
  which the classifier scores for sentiment, materiality and event types.
* **Structured filings** (Form 4, 13F, 10-K/10-Q XBRL) are parsed straight into tables with no
  language model involved.

## Data flow, step by step

1. **Reference data.** `sec_ticker_universe` loads SEC's ticker ↔ CIK list every morning.
   Filings are matched to tickers through CIK.
2. **Daily SEC runs** (one DAG per filing family, run once per filing date):
   1. skip weekends (short-circuit)
   2. wait for SEC's daily index (a sensor that frees its worker between checks)
   3. list that day's filings for the family's form types and write the list to the landing zone
   4. fetch filings in parallel batches (dynamic task mapping, throttled by the `sec_edgar` pool)
   5. parse and load each batch, recording every filing in the `sec_filings` ledger
   6. publish the family's asset
3. **RSS, hourly:** one mapped task per feed, conditional GET (ETag / Last-Modified), upsert.
4. **Classification:** `classify_articles` runs whenever the `articles` asset updates. It picks
   articles with no score for the configured `<provider>:<model>` and question set, classifies them in
   concurrent batches, then runs SQL quality checks.
5. **Live events:** after scores commit, articles rated material (≥ 2.5 of 3) and
   company-specific (≥ 0.8) are appended to the Redis Stream `eventalpha:events`, once per
   article (atomic Lua: dedupe mark + XADD).
6. **Serving:** the Spring Boot API reads the warehouse over a read-only connection and returns
   JSON with a `dataAsOf` freshness timestamp.
7. **Housekeeping, nightly:** warehouse backup, Airflow metadata cleanup, log pruning, disk check.

## Filing families

| Family / DAG | Forms | Parsed into | Notes |
|---|---|---|---|
| events · `sec_events_daily` | 8-K, 6-K, SCHEDULE 13D(/A), S-1, 424B4, 424B5 | `articles` | Body = press-release exhibits (EX-99) or the main document; 13D body = items 3–6 (purpose, source of funds, interest) from the structured XML |
| insider · `sec_insider_daily` | 4, 4/A | `insider_transactions` | One row per transaction line; code P = open-market buy, S = sale |
| holdings · `sec_holdings_daily` | 13F-HR(/A) | `institutional_filings`, `institutional_holdings` | Keyed by CUSIP; quarterly with up to 45 days' lag, so for positioning visuals, not signals |
| periodic · `sec_periodic_daily` | 10-K, 10-Q (+/A) | `report_sections`, `financial_facts` | Risk Factors and MD&A text; headline XBRL facts from SEC's companyfacts API for this filing only |

## Warehouse tables

| Table | Grain | Written by |
|---|---|---|
| `ticker_universe` | ticker | `sec_ticker_universe` |
| `sec_filings` | SEC accession (ingestion ledger: loaded / skipped / failed + reason) | all SEC DAGs |
| `articles` | (source, source_id) | events DAG, RSS DAG |
| `article_scores` | (article, `<provider>:<model>`, questions_version) | `classify_articles` |
| `feed_state` | feed URL (ETag / Last-Modified) | RSS DAG |
| `insider_transactions` | (accession, row_no) | insider DAG |
| `institutional_filings`, `institutional_holdings` | accession; (accession, row_no) | holdings DAG |
| `report_sections` | (accession, section) | periodic DAG |
| `financial_facts` | (accession, concept, unit, period); unique with `NULLS NOT DISTINCT` | periodic DAG |

## Classification

The pipeline talks to a provider-neutral interface in `src/eventalpha/classification/`:
`questions.py` (what we ask, as choice / scale / yes-no questions), `base.py` (the `Classifier`
protocol, the result shape, the scoring loop) and `providers/` (one adapter per vendor; only
these import a vendor SDK). `CLASSIFIER_PROVIDER` selects the adapter, currently `typesafe`, and
`CLASSIFIER_MODEL` overrides its pinned default. Adding another provider means one new module
plus an entry in `providers.PROVIDERS`.

One request per article; every question is answered in the same call.

| Question | Kind | Stored as |
|---|---|---|
| `sentiment` | Choice: bullish / bearish / neutral | label, all three probabilities, `sentiment_score = p_bullish − p_bearish`, confidence |
| `materiality` | Scale, 4 levels (routine → major) | expected level 0–3 and confidence |
| `company_specific` | Yes/no | probability; separates company news from macro noise |
| `event_*` (9 types) | one yes/no each: earnings, guidance up/down, M&A, exec change, capital raise/return, legal/regulatory, restructuring | `events` JSONB of probabilities |

Scores are keyed on the provider-qualified model id (`<provider>:<model version>`) and `QUESTIONS_VERSION`.
Changing either one re-classifies history into new rows, and nothing is overwritten.

## Live event stream (Redis)

| Piece | Behaviour |
|---|---|
| Producer | `classify_articles` → `eventalpha.event_stream.publish_alerts`: Lua script does `SET alerted:<id> NX EX 30d` and `XADD … MAXLEN ~ 10000` as one step, so a retried task never duplicates and a crash can't lose an event between the two |
| SSE consumer | `GET /api/v1/stream/events`: one virtual thread per client polls `XREAD` after the last ID it sent; browsers resend `Last-Event-ID` on reconnect and get exactly what they missed. Keepalive comment every 15 s; client cap (100) |
| Telegram consumer | Consumer group `telegram` (`XREADGROUP`, `XACK`). Entries that fail to send stay pending and are retried first, including after a restart. Enabled only when `TELEGRAM_BOT_TOKEN` is set |
| Redis config | AOF persistence (`appendonly yes`), `maxmemory 200mb`, `noeviction` (losing stream entries or dedupe keys silently would be worse than a write error) |

Why a stream and not Postgres `LISTEN/NOTIFY`: notifications are fire-and-forget, so a
consumer that's offline misses them. A stream keeps history and per-group delivery state.

## Market data, macro and calendars

| Area | Module | Source | Notes |
|---|---|---|---|
| Quotes, daily bars, session calendar, earnings dates | `marketdata/` (interface) + `providers/tradier.py` | Tradier brokerage API (`TRADIER_BROKER_KEY`) | Provider-neutral like the classifier (`MARKET_DATA_PROVIDER`). Tradier returns a single result as an object and empty results as `null`; `_as_list` normalizes both. The calendar only covers the current year. |
| Macro series | `macro/fred.py`, `macro/bls.py` | FRED (`FRED_API_KEY`), BLS API v2 (`BLS_API_KEY` optional) | FRED daily market series lag ~1 day; BLS seasonally adjusted CPI gives same-morning m/m |
| Release calendar | `macro/bls.py`, `calendars.py` | BLS iCalendar (exact ET times), FRED release dates (exact names), Fed FOMC page | FRED lists its FOMC release daily, so FOMC dates come from the Fed |
| Inflation nowcasts | `macro/nowcast.py` | Cleveland Fed chart JSON (`nowcast_month/quarter/year.json`) | One row per (horizon, period, measure, vintage); `actual` fills in after release |
| Trading days | `sessions.py` | `market_sessions` table | Close-relative jobs are scheduled at both candidate times; a gate lets only the right one run |

Free calendar feeds (yfinance, ForexFactory's `faireconomy`) are unofficial, so
this public project uses the official sources above instead (no consensus forecasts as a result).

## Signals

`signals/` builds the two trading-day alerts (`build.py`), reads inputs with their freshness
(`inputs.py`), renders Telegram HTML (`render.py`), and loads the SPX top-100 list
(`universe.py`, `config/spx_universe.yaml`). Each signal is stored in `signals` with its full
payload and the timestamp of every input, so it can be replayed and evaluated.

| Signal | Window | Score | Confidence |
|---|---|---|---|
| `spx_overnight` | Previous session's signal time → now | 0.6 × top-100 news (sentiment × market-cap weight × materiality) + 0.4 × breadth (all company-specific news × materiality), clipped to [-1, 1] | scored share × (0.4 × news volume + 0.6 × top-100 companies covered) |
| `premarket` | Previous session's close → 09:15 | Materiality-weighted news tone (context; the ranked list is the product) | News volume |

## Repository layout

| Path | What's there |
|---|---|
| `dags/` | DAG wiring only. `sec_edgar_daily.py` generates the four SEC DAGs; `eventalpha_common.py` holds assets, the DB engine, shared `DEFAULT_ARGS` (retries + Telegram alert) |
| `src/eventalpha/sec/` | `client` (rate-limited, retrying HTTP), `index` (daily index), `submission` (streamed submission parsing), `events`, `form4`, `form13f`, `periodic`, `families` (batch processing + ledger) |
| `src/eventalpha/` | `classification/` (questions, interface, providers), `marketdata/`, `macro/` (FRED, BLS, nowcast), `calendars.py`, `sessions.py`, `signals/`, `sources/rss`, `event_stream` (Redis Stream publisher), `db` (upserts, delete-and-insert per filing), `landing` (raw JSONL to disk or bucket), `alerts` (Telegram, healthchecks.io), `models`, `schema` |
| `migrations/` | Alembic: the source of truth for the schema |
| `api/` | Spring Boot 4 read API (Java 25, Gradle Kotlin DSL, version catalog, Testcontainers tests); `stream/` holds the SSE endpoint and Telegram relay |
| `scripts/export-schema.sh` | Exports Alembic's DDL for the Java tests (CI fails if it's stale) |
| `config/feeds.yaml` | RSS feed list: add a feed, get a mapped task |
| `docker/` | Airflow image: official 3.4.0 + pipeline deps (uv) + `pg_dump` 18 + baked-in code |
| `docker-compose.yml` | Base stack in production shape (images, no source mounts, nothing published) |
| `docker-compose.override.yml` | Local dev layer, loaded automatically: builds from source, live code mounts, localhost ports, no Airflow login |
| `docker-compose.prod.yml` | Server layer: Caddy, DuckDNS updater, data on the attached disk, memory limits, log rotation |
| `deploy/` | `Caddyfile` (HTTPS, public paths only), `deploy.sh` (deploy / roll back a commit) |
| `infra/` | Terraform for Lightsail (instance, static IP, disk, firewall, bucket), `bootstrap.sh` (first boot) |
| `.github/workflows/ci.yml` | Lint, tests, migration checks, schema sync, DAG import check; images to GHCR on `main` |
| `tests/` | pytest, with respx for HTTP mocking |

## Design decisions

| Concern | Decision |
|---|---|
| Re-runs and backfills | Every load is an upsert on a natural key, or delete-and-insert per filing for child rows (an amended filing can have fewer lines). Raw files are written atomically. Any run can be repeated safely. |
| Time semantics | SEC DAGs use `CronDataIntervalTimetable("0 1 * * *", timezone=America/New_York)`: the data interval is the filing date (Eastern), so `airflow backfill create` rebuilds any range. All schedules are New York time, so they stay put across daylight saving; storage and run IDs stay UTC. |
| One DAG per family | Generated from one file, so each family is scheduled, paused and backfilled on its own (two years of 13F without re-fetching every 8-K). |
| Waiting on SEC | Sensor in `reschedule` mode (no worker held while waiting); `soft_fail` turns holidays into skips. |
| Rate limits | Airflow pools bound the total concurrency (`sec_edgar` shared by all SEC DAGs, under SEC's 10 req/s, with `priority_weight` per family so intraday filings and 8-Ks run before 13F holdings; `classifier_api` for classification); each client also throttles itself. |
| Bandwidth | EDGAR submissions are streamed and cut off before XBRL, images and archives. RSS uses conditional GET. |
| Partial failure | A bad filing is recorded in the ledger and skipped; a batch fails (and retries) only when most of it fails. One dead feed doesn't block the others (`all_done`). |
| Data-aware scheduling | Classification is triggered by the `articles` asset, not a clock. Assets are name-only (`eventalpha.<table>`): a URI would make Airflow load every installed provider's URI handlers at parse time. |
| Fast DAG parsing | Tasks re-parse their DAG file at start, so DAG files import only a stdlib-only registry (`sec/registry.py`); heavy libraries are imported inside tasks; the image precompiles bytecode. |
| Data quality | `SQLColumnCheckOperator` / `SQLTableCheckOperator` as tasks: probability ranges, sums to one, label = argmax. |
| Schema contract | Python (Alembic) owns the DDL; Java tests run against the exported DDL in Postgres 18 via Testcontainers. |
| Read-only serving | The API's connection pool is read-only; writes belong to the pipeline. |
| Live delivery | Redis Stream with resumable SSE and an acknowledged consumer group for Telegram |
| Freshness | Every API response carries `dataAsOf` (newest ingest or score) and `generatedAt`. |
| Public API protection | Caddy exposes only `/api`, docs and health; per-IP rate limit in the app (120/min). |
| Sources | Only sources that allow automated access (SEC EDGAR, syndicated RSS). No scraping. |

## Running in production

```
internet :80/:443 ──► Caddy (Let's Encrypt) ──► Spring API          https://eventalpha.duckdns.org
operator ──► ssh -L 8080:localhost:8080 ──► Airflow UI               (never public)
attached disk /srv/eventalpha: both Postgres databases, Redis AOF, logs, raw data, Caddy certificates
Lightsail bucket: raw/ landing files + warehouse/ nightly pg_dump (30-day retention)
```

* **One Lightsail instance (8 GB)** runs the compose stack. The data lives on an attached block
  disk, so the instance can be replaced or resized without a restore.
* **Images** are built by CI on `main`, tagged with the commit SHA, and pushed to GHCR.
* **Deploys and rollbacks** are `deploy/deploy.sh [sha]` from a laptop (SSH is only open to the
  operator's IP).
* **Migrations** run on every deploy before the scheduler and API start.
* **Monitoring:** Telegram alert on any task's final failure, a healthchecks.io dead-man's
  switch for the daily SEC run, and a Telegram disk alert at 80%.

## Known limitations

* The ticker universe is today's list, so backfills miss delisted companies (survivorship bias).
* 13F holdings are keyed by CUSIP; there's no free official CUSIP → ticker map.
* 10-K/10-Q section extraction relies on item headings and misses unusual layouts.
* Single server: no high availability. Scaling path: CeleryExecutor or KubernetesExecutor, or
  managed Airflow (MWAA / Cloud Composer), with no change to DAG code.
