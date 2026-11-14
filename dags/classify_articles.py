"""
### Classify new articles with Jev, then check the output

Triggered by the `eventalpha.articles` asset (no clock schedule): runs whenever EDGAR or RSS lands data.

`plan_batches ─► classify_batch[ids] ─► publish ─► quality checks`

* **Work queue, not time window:** selects articles with no score for the pinned
  (model, questions_version), so a failed or skipped run is caught up by the next one, and
  bumping `QUESTIONS_VERSION` or `JEV_MODEL` re-classifies history automatically.
* **Pool `jev_api`** bounds concurrent batches; each batch runs async requests under a semaphore.
* **High-impact events** (material, company-specific) are appended to the Redis Stream
  `eventalpha:events` once per article, for the API's live SSE feed and Telegram relay.
* **Quality checks** run as their own tasks (common-sql operators), so bad data fails loudly
  in the UI instead of flowing into the daily signal.
"""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.common.sql.operators.sql import SQLColumnCheckOperator, SQLTableCheckOperator
from airflow.sdk import dag, task
from eventalpha_common import ARTICLE_SCORES, ARTICLES, DB_CONN_ID, DEFAULT_ARGS, chunk, engine, settings

MAX_PER_RUN = 600
BATCH_SIZE = 25
RECENT = "scored_at > now() - interval '1 day'"


@dag(
    schedule=[ARTICLES],
    start_date=pendulum.datetime(2026, 11, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,  # two runs would pick the same unscored rows
    default_args=DEFAULT_ARGS,
    tags=["transform", "jev"],
    doc_md=__doc__,
)
def classify_articles():
    @task
    def plan_batches() -> list[list[int]]:
        from eventalpha.classify import QUESTIONS_VERSION
        from eventalpha.db import select_unscored_ids

        ids = select_unscored_ids(engine(), settings().jev_model, QUESTIONS_VERSION, MAX_PER_RUN)
        print(f"{len(ids)} articles to classify (cap {MAX_PER_RUN})")
        return chunk(ids, BATCH_SIZE)

    @task(pool="jev_api", execution_timeout=timedelta(minutes=10))
    def classify_batch(ids: list[int]) -> dict:
        import asyncio

        from typesafe_sdk import AsyncTypeSafeClient

        from eventalpha.classify import classify_articles as run
        from eventalpha.db import load_articles, upsert_scores

        articles = load_articles(engine(), ids)

        async def go():
            async with AsyncTypeSafeClient() as client:  # reads TYPESAFE_API_KEY
                return await run(client, articles, model=settings().jev_model)

        rows, failed = asyncio.run(go())
        upsert_scores(engine(), rows)
        published = 0
        if rows and settings().redis_url:  # after the commit: the stream never runs ahead of the DB
            import redis

            from eventalpha.event_stream import publish_alerts

            with redis.Redis.from_url(settings().redis_url, decode_responses=True) as r:
                published = publish_alerts(r, articles, rows)
        if rows and rows[0]["model"] != settings().jev_model:
            print(f"warning: requested {settings().jev_model}, API answered as {rows[0]['model']}")
        if articles and not rows:
            raise RuntimeError(f"all {len(articles)} classifications failed")
        tokens = sum(r["input_tokens"] or 0 for r in rows)
        return {"scored": len(rows), "failed": len(failed), "input_tokens": tokens, "alerts": published}

    @task(outlets=[ARTICLE_SCORES])
    def publish(results: list[dict]) -> dict:
        totals = {k: sum(r[k] for r in results) for k in ("scored", "failed", "input_tokens", "alerts")}
        print(totals)
        return totals

    column_checks = SQLColumnCheckOperator(
        task_id="check_score_ranges",
        conn_id=DB_CONN_ID,
        table="article_scores",
        partition_clause=RECENT,
        column_mapping={
            col: {"null_check": {"equal_to": 0}, "min": {"geq_to": 0}, "max": {"leq_to": 1}}
            for col in ("p_bullish", "p_bearish", "p_neutral", "sentiment_confidence", "company_specific")
        }
        | {"materiality": {"min": {"geq_to": 0}, "max": {"leq_to": 3}}},
    )
    table_checks = SQLTableCheckOperator(
        task_id="check_score_consistency",
        conn_id=DB_CONN_ID,
        table="article_scores",
        partition_clause=RECENT,
        checks={
            "known_sentiment": {"check_statement": "sentiment IN ('bullish', 'bearish', 'neutral')"},
            "probabilities_sum_to_one": {"check_statement": "abs(p_bullish + p_bearish + p_neutral - 1) < 0.02"},
            "label_matches_argmax": {
                "check_statement": "CASE sentiment WHEN 'bullish' THEN p_bullish WHEN 'bearish' THEN p_bearish "
                "ELSE p_neutral END >= greatest(p_bullish, p_bearish, p_neutral) - 1e-6"
            },
        },
    )

    publish(classify_batch.expand(ids=plan_batches())) >> [column_checks, table_checks]


classify_articles()
