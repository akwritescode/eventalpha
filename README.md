# EventAlpha

[![CI](https://github.com/akwritescode/eventalpha/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/akwritescode/eventalpha/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196.svg)](https://www.conventionalcommits.org)
![Airflow 3](https://img.shields.io/badge/Airflow-3-017CEE.svg)
![Java 25 · Spring Boot 4](https://img.shields.io/badge/Java%2025-Spring%20Boot%204-6DB33F.svg)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg)

**Open-source, event-driven quant intelligence.** EventAlpha collects corporate events from
SEC EDGAR and syndicated news feeds, classifies the text ones with
a pluggable classifier (sentiment, materiality, event types; currently
[TypeSafe](https://docs.typesafe.ai/introduction)),
and serves the results through a read API for next-day trading research.

Sources are limited to ones that allow automated access: SEC EDGAR (public data under its
[fair-access policy](https://www.sec.gov/os/accessing-edgar-data)) and RSS feeds published
for syndication. No scraping.

![The Market Intelligence Stream: trading signals, SEC filings, news and macro releases in one
feed, with news sentiment, an economic and earnings calendar, the inflation nowcast and insider
buying alongside (shown with the demo data from `make seed`)](docs/images/stream.jpg)

| Layer | Stack |
|---|---|
| Orchestration | Apache Airflow 3.4 (TaskFlow, assets, dynamic task mapping, pools) |
| Pipeline | Python 3.12, uv, httpx, lxml, feedparser, SQLAlchemy Core |
| Classification | Provider-neutral interface (`eventalpha.classification`); provider chosen by `CLASSIFIER_PROVIDER` (currently TypeSafe) |
| Warehouse | PostgreSQL 18, schema owned by Alembic |
| Live events | Redis 8 Streams (SSE feed + Telegram consumer group) |
| API | Java 25, Spring Boot 4.1, Gradle 9 (Kotlin DSL), JdbcClient, virtual threads, springdoc |
| Tests | pytest + respx; JUnit 5 + Testcontainers (Postgres 18 with the Alembic-generated DDL) |

Documentation:

* [docs/DATA_FLOW.md](docs/DATA_FLOW.md): diagrams following data from SEC and RSS to the API,
  the live stream and Telegram, with one real filing traced end to end
* [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md): requirements, scale estimates, data model,
  failure modes, scaling path
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, tables, repo layout, design decisions
* [docs/INTRADAY_DATA_DESIGN.md](docs/INTRADAY_DATA_DESIGN.md) covers minute-candle collection, move windows, partitions and verified S3 retention
* [docs/DEPLOY.md](docs/DEPLOY.md): production on Lightsail

## What it collects

| DAG | Source | Lands in |
|---|---|---|
| `sec_events_daily` | 8-K, 6-K, Schedule 13D(/A), S-1, 424B4, 424B5 | `articles` → classifier → `article_scores` |
| `sec_insider_daily` | Form 4(/A) insider transactions | `insider_transactions` |
| `sec_holdings_daily` | 13F-HR(/A) institutional holdings | `institutional_filings`, `institutional_holdings` |
| `sec_periodic_daily` | 10-K / 10-Q risk factors, MD&A, XBRL headline facts | `report_sections`, `financial_facts` |
| `rss_news_hourly` | Press-release and macro RSS feeds (`config/feeds.yaml`) | `articles` |
| `classify_articles` | Runs when `articles` changes (asset-triggered) | `article_scores` + SQL quality checks |
| `sec_ticker_universe` | SEC company tickers | `ticker_universe` |
| `sec_current_filings` | EDGAR "latest filings" feed, every 15 min 06:00-20:00 ET | `articles` (same keys as the nightly run) |
| `market_calendar` | Exchange sessions incl. holidays and 13:00 early closes (Tradier) | `market_sessions` |
| `market_snapshot_premarket` / `_close` | Quotes at 09:10 and at close + 35 min; daily bars (Tradier) | `market_snapshots`, `price_bars_daily` |
| `market_move_bars` | One-minute regular-session bars for the Nasdaq-100/S&P 500 union and benchmarks, every 15 minutes | `price_bars_minute` |
| `macro_data` | FRED series + BLS series, 08:40 and 18:00 ET | `macro_observations` |
| `inflation_nowcast` | Cleveland Fed inflation nowcasts, 10:30 ET | `inflation_nowcasts` |
| `calendars_daily` | BLS release calendar, FRED release dates, FOMC dates (Fed), earnings dates (Tradier) | `econ_events`, `earnings_events` |
| `signal_premarket` | 09:15 ET on trading days → Telegram | `signals` |
| `signal_spx_overnight` | 15 min before the SPX session ends (16:45 ET; 13:45 on early closes) → Telegram | `signals` |

Every processed SEC filing also gets a row in the `sec_filings` ledger (loaded / skipped /
failed, plus the reason), so coverage per day can be queried.

## Index membership

`config/index_members.json` lists every member of the **S&P 500, Nasdaq-100 and Dow Jones
Industrial Average** (the indexes overlap; about 518 distinct symbols). It is the coverage list
for the earnings calendar and minute candles, and it's mirrored into the `index_members` table
for SQL joins. The pipeline never fetches membership itself.

Refresh it after each quarterly rebalance (effective after the third Friday of March, June,
September and December), then re-rank the SPX signal universe from it:

```bash
WIKIMEDIA_USER_AGENT="EventAlpha index refresh (you@example.com)" \
  uv run python scripts/refresh_index_members.py   # prints members added/removed per index
uv run python scripts/refresh_spx_universe.py      # top 100 by market cap → config/spx_universe.yaml
```

Both scripts write files for review in a pull request; each index records the exact Wikipedia
revision it came from. The pipeline watchdog sends a weekly reminder once either file is more
than 100 days old.

## Minute candles and retention

`market_move_bars` covers every member of the S&P 500, Nasdaq-100 and Dow Jones Industrial
Average from the reviewed `config/index_members.json` snapshot, plus SPY, QQQ, DIA and SMH
(522 symbols). See [Index membership](#index-membership).

Collection uses two workers with 25 symbols per batch and at least 1.5 seconds between symbol
requests per worker. New members receive eight calendar days of history. Subsequent requests
overlap an hour to fill missed bars. Symbols such as BRK-B are requested as BRK/B from the provider
and stored under the SEC symbol spelling. Historical first observations are retained on retries.

`price_bars_minute` is range-partitioned by UTC day. Its migration preserves the existing candles.
Nightly maintenance archives complete days older than 14 full UTC days under
`s3://<bucket>/minute_bars/dt=YYYY-MM-DD/`. Each archive is compressed JSONL with OHLCV,
timestamps, and a manifest. The job uploads, downloads, verifies its SHA-256 checksum and row
count, verifies the manifest, and only then drops that day's partition. Daily candles stay in
`price_bars_daily` and are outside this retention job.

Set `MINUTE_ARCHIVE_BUCKET` (or use the existing `RAW_BUCKET`) and provide S3 PutObject/GetObject
access through the existing AWS configuration. When sharing a bucket across environments, set
`MINUTE_ARCHIVE_PREFIX=minute_bars/local` locally to keep production manifests separate. With neither bucket set, archival reports a skip
and retains the Postgres rows. With failed verification, the affected partition is retained and
the task retries. Archives are permanent unless the bucket has a separate lifecycle policy.
Rows in the default partition trigger an error so they cannot silently evade retention.

After updating, run warehouse migrations before unpausing `market_move_bars` and `maintenance`.
The initial collection is larger than an incremental run. The public move UI still focuses on
the past seven days and reads Postgres.

## Trading-day signals

Two Telegram alerts on trading days (New York time). Both run on the clock, never wait for
inputs, and print how fresh each input was. They're research signals, not advice.

| Time (ET) | Signal | Contents |
|---|---|---|
| 09:15 | Premarket | Companies with material news since the last close (ranked by materiality × sentiment strength), insider open-market buying (clusters), today's earnings and macro releases, CPI surprise vs the Cleveland Fed nowcast on CPI days, premarket moves |
| 16:45 (13:45 on early closes) | SPX overnight | Top-100 S&P 500 news weighted by market-cap weight, breadth of company news, next session's macro calendar and earnings, closing moves in SPX, VIX, rates, credit, oil, dollar |

The day around them: 00:15 session calendar · 00:30 tickers · 01:00 SEC daily runs (Form 4,
13F, 10-K/Q, 8-K reconciliation) · 06:00 calendars · every 15 min 06:00-20:00 intraday SEC filings
and RSS · 08:40 macro · 09:10 premarket snapshot · 10:30 inflation nowcast · close + 35 min
close snapshot · 18:00 macro.

Data sources are official or licensed: SEC EDGAR, BLS, FRED, the Federal Reserve's FOMC
calendar, the Cleveland Fed's inflation nowcasts, and the Tradier brokerage API.

## Architecture

```
 SEC EDGAR ──► sec_{events,insider,holdings,periodic}_daily ──┐      raw JSONL landing zone
 RSS feeds ──► rss_news_hourly ───────────────────────────────┤──►   data/raw/<source>/dt=YYYY-MM-DD/
                                                              │
                                        asset: articles ──────┤
                                                              ▼
                                   classify_articles (classifier, pool classifier_api) ──► SQL checks
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
| External rate limits | The `sec_edgar` pool is shared by all SEC DAGs, which keeps their combined rate under 10 req/s. Priority weights decide who gets a free slot first: intraday filings 100, ticker refresh 50, events 40, Form 4 30, 10-K/Q 20, 13F 10. `classifier_api` bounds classification. Each client also throttles itself. |
| Bandwidth | EDGAR submissions are streamed and cut off before XBRL, images and archives. RSS uses conditional GET. |
| Partial failure | A bad filing is logged in the ledger and skipped; a batch fails (and retries) only if most of it fails. |
| Model changes | Scores are keyed on `<provider>:<model>` and `QUESTIONS_VERSION`; switching provider or model, or changing the questions, re-classifies history into new rows. |
| Schema contract | Alembic owns the DDL. `scripts/export-schema.sh` exports it for the Java tests, so the API's SQL runs against the real schema. |
| Freshness | Every API response carries `dataAsOf` (newest ingest or score) next to `generatedAt`. |

## API

A public, read-only HTTP API (no key; rate limited per IP). Every response is
`{"data": ..., "dataAsOf": "<timestamp>"}` so clients can show how fresh the data is.

| Endpoint | Returns |
|---|---|
| `GET /api/v1/feed?types=sec,news,macro,signal&days=7&limit=100&ticker=` | The Market Intelligence Stream, newest first; page with `before` + `beforeId` (the last item's `occurredAt` and `id`) |
| `GET /api/v1/stream/events?stream=events\|feed` | Server-Sent Events: high-impact events, or every new stream item; resumes from `Last-Event-ID` |
| `GET /api/v1/articles?ticker=AAON&formType=8-K&days=7` | Filings and news with their latest classification |
| `GET /api/v1/events?type=guidance_lowered&minProb=0.8` | Items the classifier flags with an event type |
| `GET /api/v1/tickers/{ticker}/move-explanation?start=…&end=…&asOf=…` | Evidence around a specific move window and an optional replay cutoff. [Try the NVDA fixture](examples/README.md#move-explanation). |
| `GET /api/v1/tickers/{ticker}/sentiment?days=30` | Daily sentiment for one ticker |
| `GET /api/v1/tickers/{ticker}/insider-trades?days=90` | Form 4 transactions and net open-market value |
| `GET /api/v1/signals/latest` | The latest premarket and SPX overnight signals with their inputs |
| `GET /api/v1/stats/sentiment-daily?days=14` | Market-wide daily sentiment of company-specific news |
| `GET /api/v1/insiders/buys?days=14` | Largest open-market insider purchases, with 30-day clusters |
| `GET /api/v1/calendar/upcoming?days=14` | Economic releases and earnings dates (largest company first) |
| `GET /api/v1/macro/nowcast` | Cleveland Fed inflation nowcast, with the actual once released |
| `GET /api/v1/channel/preview?limit=20` | What the Telegram alerts channel has posted |
| `GET /api/v1/status/sec?days=14` | SEC filings processed per day and family (pipeline health) |

OpenAPI UI at http://localhost:8081/docs, health at `/actuator/health`. Request and stream
examples in Python, JavaScript and curl: [examples/](examples/README.md).

## Running locally

**Prerequisites:** Docker Desktop (or Docker Engine with Compose v2, ~8 GB RAM for Docker),
[uv](https://docs.astral.sh/uv/), Node 22, GNU Make. Java 25 only if you work on the API
outside Docker.

```bash
git clone https://github.com/akwritescode/eventalpha.git && cd eventalpha
make setup                    # git hooks, Python and web dependencies, .env from .env.example
```

Edit `.env`. Only `SEC_USER_AGENT` is required to start (SEC asks for a name and a real
contact email, e.g. `"eventalpha you@example.com"`). The API keys enable more sources:
without `TYPESAFE_API_KEY` nothing is classified, without `TRADIER_BROKER_KEY`/`FRED_API_KEY`
there are no prices or FRED series. `FERNET_KEY` may stay empty locally (Airflow then stores
connection passwords unencrypted and logs a warning); production requires one.

```bash
make up                       # first start builds the images (a few minutes)
curl -s localhost:8081/actuator/health          # {"status":"UP"} once Postgres and Redis are ready
docker compose exec airflow-scheduler airflow dags list-import-errors   # "No data found"
make seed                     # optional: demo data, so the UI isn't empty before the first runs
cd web && npm start           # web UI on http://localhost:3000
```

DAGs start paused: unpause the ones you want in the Airflow UI (http://localhost:8080) or with
`airflow dags unpause <dag_id>` (see [Common commands](#common-commands)). The
`pipeline_watchdog` DAG reports paused DAGs to the ops chat once Telegram is configured.

After editing `.env`, recreate the containers so they see the new values (Docker reads
`env_file` only when it creates a container):

```bash
docker compose up -d --force-recreate
```

### What's where locally

Everything listens on `127.0.0.1` only.

| What | Where | Notes |
|---|---|---|
| **Airflow UI** | http://localhost:8080 | No login locally. Dags, runs, task logs, **Assets**, **Admin → Pools / Connections**. Set the UI timezone to New York (user menu, bottom left) so schedules and run times read the same |
| **API docs (Swagger UI)** | http://localhost:8081/docs | Try every endpoint in the browser; `http://localhost:8081/` redirects here |
| OpenAPI spec | http://localhost:8081/openapi | JSON, for client generators |
| API health | http://localhost:8081/actuator/health | `UP` when Postgres and Redis are reachable |
| Live event stream | `curl -N http://localhost:8081/api/v1/stream/events` | Server-Sent Events: prints `:connected`, then each high-impact event as it's published |
| **Warehouse (Postgres 18)** | `localhost:5433`, db / user / password `eventalpha` | Postico, DBeaver, `psql -h localhost -p 5433 -U eventalpha` |
| **Web UI** | http://localhost:3000 | Not in Compose: `cd web && npm start`, see [Web UI](#web-ui-market-intelligence-stream) |
| **Redis Insight** | http://localhost:5540 | Optional, see below |
| Task logs (files) | `./logs/dag_id=…/run_id=…/task_id=…/attempt=N.log` | Same logs as the Airflow UI |
| Raw landing zone | `./data/raw/<source>/dt=YYYY-MM-DD/*.jsonl` | What each run fetched, before any database write |
| Alerts | Telegram | Signals and high-impact events to the channel (`TELEGRAM_CHAT_ID`); task failures, paused DAGs and disk alerts to the ops chat (`TELEGRAM_OPS_CHAT_ID`) |

Airflow's own metadata database (`airflow-db`) isn't exposed; use the Airflow UI or
`docker compose exec airflow-db psql -U airflow`.

### Common commands

Schedules are in New York time (the SEC DAGs run at 01:00 ET for the previous filing date).
DAGs start paused: unpause them in the Airflow UI, or from the command line.

```bash
alias af='docker compose exec airflow-scheduler airflow'

af dags list-import-errors                      # should print "No data found"
af dags trigger sec_ticker_universe             # run once now
af dags unpause signal_premarket                # start a DAG's schedule
af backfill create --dag-id sec_insider_daily \
  --from-date 2026-11-02T01:00:00-05:00 --to-date 2026-11-13T01:00:00-05:00   # filing dates, 01:00 ET
af dags trigger signal_spx_overnight \
  --conf '{"as_of": "2026-11-13T16:45:00-05:00"}' # replay a signal as of a past trading-day moment

docker compose ps                                # container health
docker compose logs -f --tail 100 api            # follow a service's logs
```

### Web UI (Market Intelligence Stream)

React 18 + TypeScript + MUI 5 + Recharts (Create React App), in `web/`.
The web app isn't in Docker Compose locally; run it with the Node dev server next to the stack.

**Run it** (Node 20+; the API must be up on :8081, i.e. `docker compose up -d` first):

```bash
cd web
npm install                      # first time only
cp .env.example .env.local       # first time only: API URL (http://localhost:8081) + Telegram invite link
npm start                        # → opens http://localhost:3000, reloads on save
```

Stop it with Ctrl-C. If it says *"Something is already running on port 3000"*, an old dev server
is still alive: `lsof -ti :3000 | xargs kill`, then `npm start` again.

**What to look at** on http://localhost:3000:

* **The stream**: SEC filings, news, released macro data (forecast / actual / surprise) and
  trading signals, newest first, grouped by day. Tabs filter by type; click a card to expand its
  facts, probabilities, a signal's contributing events and related events (shared tickers, ±3 days).
  "Load more" pages back in time.
* **Side rail**: daily sentiment chart, upcoming calendar, CPI nowcast, recent insider buys.
* **Subscribe to Alerts** (top bar): previews what's been posted to the Telegram channel, with
  "Join on Telegram" at the bottom.
* **Bell** (top bar): browser notifications — *High-impact*, *Everything* or *Off*. Allow
  notifications when the browser asks. They fire while the site is open in any tab; the tab
  title shows the unseen count.
* **Live updates**: new items are pushed over Server-Sent Events (`/api/v1/stream/events?stream=feed`),
  so the page needs no refresh. The LIVE / OFFLINE badge above the stream shows whether the connection is up.
* **Mobile**: the layout works at phone width (DevTools device toolbar, or your phone on the
  same network via `http://<your-mac-ip>:3000` after adding that origin to
  `EVENTALPHA_CORS_ALLOWED_ORIGINS` in `.env`, e.g.
  `http://localhost:3000,http://192.168.1.20:3000`, then `docker compose up -d --force-recreate api`).

**See a notification without waiting for real data**: push a test item onto the feed stream,
then delete it:

```bash
docker compose exec redis redis-cli XADD eventalpha:feed '*' kind sec ref test:1 \
  title "Test filing" label "SEC · 8-K" tickers AAPL impact high sentiment bullish url "" occurred_at ""
docker compose exec redis redis-cli XDEL eventalpha:feed <id printed above>
```

Before shipping: `CI=true npm run build` (fails on any lint warning).

### Looking at Redis (the live event stream)

[Redis Insight](https://redis.io/insight/) is an optional local service. A plain
`docker compose up -d` doesn't start it; start it when you need it:

```bash
docker compose --profile tools up -d redisinsight   # → http://localhost:5540
```

First time only, in the UI: **Add Redis database** → add manually →
**Host `redis`** (the Docker service name, not `localhost`), **Port `6379`**, alias
`eventalpha`, no username or password. The connection is saved in a volume.

Then open **Browser** → key `eventalpha:events` (a Stream) to see published high-impact
events and, under *Consumer Groups*, the `telegram` group with its pending and delivered entries.

Without the GUI:

```bash
docker compose exec redis redis-cli XRANGE eventalpha:events - + COUNT 5   # first 5 events
docker compose exec redis redis-cli XINFO GROUPS eventalpha:events          # consumer groups, lag
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
images on `main`; deploys and rollbacks are one command from a laptop. The web UI is on
Vercel, deployed from GitHub on every push (preview builds per pull request), and calls the
API directly. See [docs/DEPLOY.md](docs/DEPLOY.md).

## Layout

```
dags/                 DAG wiring only; logic lives in the package
src/eventalpha/       sec/ (client, index, submission, events, form4, form13f, periodic, families),
                      classification/ (questions, interface, providers/), sources/rss, db (loaders), landing (raw JSONL)
migrations/           Alembic
api/                  Spring Boot read API (Gradle, Kotlin DSL, version catalog)
config/feeds.yaml     RSS feeds: add one here and a mapped task appears
docker/               Airflow image (official 3.4.0 + pipeline deps via uv, code baked in)
infra/                Terraform for Lightsail, first-boot bootstrap script
deploy/               Caddyfile, deploy.sh
docker-compose*.yml   base (production shape) · override (local dev, auto-loaded) · prod
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) (setup, Conventional Commits, checks) and the
[Code of Conduct](CODE_OF_CONDUCT.md). Security issues: [SECURITY.md](SECURITY.md). Design
decisions and their trade-offs are recorded in [docs/adr](docs/adr/README.md).

## License

Apache License 2.0: see [LICENSE](LICENSE) and [NOTICE](NOTICE). You may use, modify and
redistribute the code, including commercially, as long as you keep the license and notices;
the license also includes an explicit patent grant. It covers the code only, not the data the
pipeline fetches, which stays under each source's own terms (listed in NOTICE).

## Attribution

Inflation nowcasts: Federal Reserve Bank of Cleveland, Inflation Nowcasting
(doi:10.26509/frbc-inflationnowcast), used for non-commercial research with attribution.
Economic data: U.S. Bureau of Labor Statistics; FRED, Federal Reserve Bank of St. Louis.

## Known limitations

* The ticker universe is today's SEC list, so backfills miss companies that have since
  delisted (survivorship bias).
* 13F holdings are keyed by CUSIP; SEC doesn't publish a CUSIP→ticker map.
* 10-K/10-Q section extraction relies on item headings and misses unusual layouts.
* The SPX top-100 list (`config/spx_universe.yaml`) approximates S&P's float-adjusted weights
  (price × SEC share counts); they aren't the official licensed weights.
* Index membership comes from Wikipedia's constituent tables and changes only when the snapshot
  is refreshed, so a member added mid-quarter is missed until the next refresh.
* The earnings calendar gives dates, not before-open/after-close timing.
* Tradier's session calendar only covers the current year, so next January loads once the year turns.
* No free official source publishes consensus forecasts; CPI surprise is measured against the
  Cleveland Fed nowcast instead.
* The web UI is built with Create React App, which is no longer maintained; moving to Vite is
  planned work (Dependabot holds back major upgrades of the UI stack until then).

## Roadmap

1. Daily price bars for tickers in the news, plus SPY/QQQ, from a licensed market-data API
2. `daily_sentiment_signal`: per-ticker aggregate after the close, then next-day brief
3. `sentiment_eval`: does sentiment predict next-day returns? Calibration by event type
4. Year-over-year diffs of 10-K risk-factor text scored by the classifier ("Lazy Prices")
5. 13F positioning and crowding visuals (separate UI project)
