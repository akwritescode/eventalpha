"""
### RSS press releases and macro feeds, hourly

`load feeds ─► ingest_feed[feed] (one mapped task per feed) ─► publish`

* **Dynamic task mapping:** adding a feed to `config/feeds.yaml` adds a task, no DAG edit.
* **Conditional GET:** ETag / Last-Modified stored per feed, so unchanged feeds cost a 304.
* **Isolation:** a dead feed fails (and retries) on its own; `publish` runs with
  `all_done`, so one broken feed never blocks classification of the others.
* Feeds only expose their latest items, so this DAG can't backfill. EDGAR covers history.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, get_current_context, task
from eventalpha_common import ARTICLES, DEFAULT_ARGS, engine, settings


@dag(
    schedule="5 * * * *",
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["ingest", "rss"],
    doc_md=__doc__,
)
def rss_news_hourly():
    @task
    def load_feed_list() -> list[dict]:
        from dataclasses import asdict

        from eventalpha.feeds import load_feeds

        return [asdict(f) for f in load_feeds(Path(os.environ["FEEDS_CONFIG"]))]

    @task(max_active_tis_per_dagrun=8, execution_timeout=timedelta(minutes=5))
    def ingest_feed(feed: dict) -> dict:
        import httpx

        from eventalpha.db import get_feed_state, save_feed_state, upsert_articles
        from eventalpha.landing import write_jsonl
        from eventalpha.sources.rss import Feed, entry_to_article, fetch_feed

        f = Feed(**feed)
        ctx = get_current_context()
        state = get_feed_state(engine(), f.url) or {}
        headers = {"User-Agent": settings().sec_user_agent}
        with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
            result = fetch_feed(client, f.url, state.get("etag"), state.get("last_modified"))
        if result.status == 304:
            save_feed_state(engine(), f.url, result.etag, result.last_modified, 304)
            return {"feed": f.name, "status": 304, "inserted": 0, "updated": 0}

        articles = [a for e in result.entries if (a := entry_to_article(f, e))]
        write_jsonl(
            settings().raw_data_dir, f"rss_{f.name}", ctx["logical_date"].date(), ctx["run_id"],
            (a.model_dump(mode="json") for a in articles), bucket=settings().raw_bucket,
        )
        counts = upsert_articles(engine(), articles)
        # Save the ETag only after the load commits: a crash before this just re-fetches next run.
        save_feed_state(engine(), f.url, result.etag, result.last_modified, result.status)
        return {"feed": f.name, "status": result.status, **counts}

    @task(outlets=[ARTICLES], trigger_rule="all_done")
    def publish() -> None:
        """Emits the asset event that triggers classification."""

    ingest_feed.expand(feed=load_feed_list()) >> publish()


rss_news_hourly()
