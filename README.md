# EventAlpha

**Open-source, event-driven quant intelligence.** EventAlpha collects corporate events from
SEC EDGAR and syndicated news feeds, classifies the text ones with
[TypeSafe Jev](https://docs.typesafe.ai/introduction) (sentiment, materiality, event types),
and serves the results through a read API for next-day trading research.

Sources are limited to ones that allow automated access: SEC EDGAR (public data under its
[fair-access policy](https://www.sec.gov/os/accessing-edgar-data)) and RSS feeds published
for syndication. No scraping.

| Layer | Stack |
|---|---|
| Orchestration | Apache Airflow 3.4 (TaskFlow, assets, dynamic task mapping, pools) |
| Pipeline | Python 3.12, uv, httpx, lxml, feedparser, SQLAlchemy Core, TypeSafe SDK |
| Warehouse | PostgreSQL 18, schema owned by Alembic |
| Live events | Redis 8 Streams (SSE feed + Telegram consumer group) |
| API | Java 25, Spring Boot 4.1, Gradle 9 (Kotlin DSL), JdbcClient, virtual threads, springdoc |
| Tests | pytest + respx; JUnit 5 + Testcontainers (Postgres 18 with the Alembic-generated DDL) |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design (data flow, tables,
repo layout, design decisions) and [docs/DEPLOY.md](docs/DEPLOY.md) for production.

## What it collects

| DAG | Source | Lands in |
|---|---|---|
| `sec_events_daily` | 8-K, 6-K, Schedule 13D(/A), S-1, 424B4, 424B5 | `articles` → Jev → `article_scores` |
| `sec_insider_daily` | Form 4(/A) insider transactions | `insider_transactions` |
| `sec_holdings_daily` | 13F-HR(/A) institutional holdings | `institutional_filings`, `institutional_holdings` |
| `sec_periodic_daily` | 10-K / 10-Q risk factors, MD&A, XBRL headline facts | `report_sections`, `financial_facts` |
| `rss_news_hourly` | Press-release and macro RSS feeds (`config/feeds.yaml`) | `articles` |
| `classify_articles` | Runs when `articles` changes (asset-triggered) | `article_scores` + SQL quality checks |
| `sec_ticker_universe` | SEC company tickers | `ticker_universe` |

Every processed SEC filing also gets a row in the `sec_filings` ledger (loaded / skipped /
failed, plus the reason), so coverage per day can be queried.

## Architecture

```
 SEC EDGAR ──► sec_{events,insider,holdings,periodic}_daily ──┐      raw JSONL landing zone
 RSS feeds ──► rss_news_hourly ───────────────────────────────┤──►   data/raw/<source>/dt=YYYY-MM-DD/
                                                              │
                                        asset: articles ──────┤
                                                              ▼
                                   classify_articles (Jev, pool jev_api) ──► SQL checks
                                                              │
                                          PostgreSQL 18 warehouse (Alembic)
                                                              │ read-only
                                               Spring Boot API :8081 (/docs)
```

### Design choices

| Concern | How it's handled |
|---|---|
| Re-runs / backfills | Loads are upserts on natural keys, or delete-and-insert per filing for child rows (amendments can drop lines). Raw files are written atomically. Any run can be repeated. |
| Time semantics | SEC DAGs use `CronDataIntervalTimetable`: the data interval *is* the filing date, so `airflow backfill create` rebuilds any range. |
| One file, four DAGs | `dags/sec_edgar_daily.py` generates a DAG per filing family, so 13F history can be backfilled without re-fetching every 8-K. |
| Waiting for upstream | A `reschedule`-mode sensor waits for SEC's evening index without holding a worker; `soft_fail` turns holidays into skips. |
| External rate limits | The `sec_edgar` pool is shared by all SEC DAGs, which keeps their combined rate under 10 req/s. `jev_api` bounds classification. Each client also throttles itself. |
| Bandwidth | EDGAR submissions are streamed and cut off before XBRL, images and archives. RSS uses conditional GET. |
| Partial failure | A bad filing is logged in the ledger and skipped; a batch fails (and retries) only if most of it fails. |
| Model changes | Scores are keyed on the Jev version and `QUESTIONS_VERSION`; changing either re-classifies history into new rows. |
| Schema contract | Alembic owns the DDL. `scripts/export-schema.sh` exports it for the Java tests, so the API's SQL runs against the real schema. |
| Freshness | Every API response carries `dataAsOf` (newest ingest or score) next to `generatedAt`. |

## API

```
GET /api/v1/articles?ticker=AAON&formType=8-K&days=7
GET /api/v1/events?type=guidance_lowered&minProb=0.8
GET /api/v1/tickers/{ticker}/sentiment?days=30
GET /api/v1/tickers/{ticker}/insider-trades?days=90&openMarketOnly=true
GET /api/v1/status/sec?days=14
GET /api/v1/stream/events          # Server-Sent Events; resumes from Last-Event-ID
```

OpenAPI UI at http://localhost:8081/docs, health at `/actuator/health`.

## Running locally

```bash
cp .env.example .env          # set SEC_USER_AGENT (real contact email) and TYPESAFE_API_KEY
docker compose up -d          # Airflow http://localhost:8080 (local-only, no login), API :8081
```

DAGs start paused. Run `sec_ticker_universe` first, then unpause the others or backfill:

```bash
docker compose exec airflow-scheduler airflow dags trigger sec_ticker_universe
docker compose exec airflow-scheduler airflow backfill create --dag-id sec_insider_daily \
  --from-date 2026-11-02T06:00:00+00:00 --to-date 2026-11-13T06:00:00+00:00
```

Development:

```bash
uv sync && uv run pytest && uv run ruff check .                 # Python
uv run alembic revision --autogenerate -m "..." && ./scripts/export-schema.sh
cd api && ./gradlew test                                        # Java (JDK 25 auto-provisioned)
```

## Deployment

A single AWS Lightsail instance runs the same compose stack with a production layer (Caddy +
Let's Encrypt on a DuckDNS name, data on an attached disk, backups to a bucket). CI builds
images on `main`; deploys and rollbacks are one command from a laptop. See
[docs/DEPLOY.md](docs/DEPLOY.md).

## Layout

```
dags/                 DAG wiring only; logic lives in the package
src/eventalpha/       sec/ (client, index, submission, events, form4, form13f, periodic, families),
                      sources/rss, classify (Jev), db (loaders), landing (raw JSONL)
migrations/           Alembic
api/                  Spring Boot read API (Gradle, Kotlin DSL, version catalog)
config/feeds.yaml     RSS feeds: add one here and a mapped task appears
docker/               Airflow image (official 3.4.0 + pipeline deps via uv, code baked in)
infra/                Terraform for Lightsail, first-boot bootstrap script
deploy/               Caddyfile, deploy.sh
docker-compose*.yml   base (production shape) · override (local dev, auto-loaded) · prod
```

## Known limitations

* The ticker universe is today's SEC list, so backfills miss companies that have since
  delisted (survivorship bias).
* 13F holdings are keyed by CUSIP; SEC doesn't publish a CUSIP→ticker map.
* 10-K/10-Q section extraction relies on item headings and misses unusual layouts.

## Roadmap

1. Daily price bars for tickers in the news, plus SPY/QQQ, from a licensed market-data API
2. `daily_sentiment_signal`: per-ticker aggregate after the close, then next-day brief
3. `sentiment_eval`: does sentiment predict next-day returns? Calibration by event type
4. Year-over-year diffs of 10-K risk-factor text scored by Jev ("Lazy Prices")
5. 13F positioning and crowding visuals (separate UI project)
