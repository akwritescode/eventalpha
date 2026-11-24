"""
### Classify new articles, then check the output

Triggered by the `eventalpha.articles` asset (no clock schedule): runs whenever EDGAR or RSS lands data.

`plan_batches ─► classify_batch[ids] ─► publish ─► quality checks`

* **Work queue, not time window:** selects articles with no score for the pinned
  (model, questions_version), so a failed or skipped run is caught up by the next one, and
  bumping `QUESTIONS_VERSION`, `CLASSIFIER_MODEL` or `CLASSIFIER_PROVIDER` re-classifies history
  automatically (scores are stored under "<provider>:<model>").
* **Provider-neutral:** the DAG talks to `eventalpha.classification`; the provider (and its SDK)
  is chosen by `CLASSIFIER_PROVIDER`.
* **Pool `classifier_api`** bounds concurrent batches; each batch runs async requests under a semaphore.
* **High-impact events** (material, company-specific, with an S&P 500 or Nasdaq-100 ticker) are appended to
  the Redis Stream `eventalpha:events` once per article, for the API's live SSE feed and Telegram relay.
* **Quality checks** run as their own tasks (common-sql operators), so bad data fails loudly
  in the UI instead of flowing into the daily signal.
"""

from __future__ import annotations

from datetime import timedelta

from airflow.providers.common.sql.operators.sql import SQLColumnCheckOperator, SQLTableCheckOperator
from airflow.sdk import dag, task
from eventalpha_common import (
    ARTICLE_SCORES,
    ARTICLES,
    DB_CONN_ID,
    DEFAULT_ARGS,
    START_DATE,
    chunk,
    engine,
    index_members,
    settings,
)

MAX_PER_RUN = 600
BATCH_SIZE = 25
RECENT = "scored_at > now() - interval '1 day'"


@dag(
    schedule=[ARTICLES],
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,  # two runs would pick the same unscored rows
    default_args=DEFAULT_ARGS,
    tags=["transform", "classification"],
    doc_md=__doc__,
)
def classify_articles():
    @task
    def plan_batches() -> list[list[int]]:
        from eventalpha.classification import QUESTIONS_VERSION, resolve_model_id
        from eventalpha.db import select_unscored_ids

        model_id = resolve_model_id(settings().classifier_provider, settings().classifier_model)
        ids = select_unscored_ids(engine(), model_id, QUESTIONS_VERSION, MAX_PER_RUN)
        print(f"{len(ids)} articles to classify with {model_id} (cap {MAX_PER_RUN})")
        return chunk(ids, BATCH_SIZE)

    @task(pool="classifier_api", execution_timeout=timedelta(minutes=10))
    def classify_batch(ids: list[int]) -> dict:
        import asyncio

        from eventalpha.classification import classify_articles as run
        from eventalpha.classification import create_classifier
        from eventalpha.db import load_articles, upsert_scores

        articles = load_articles(engine(), ids)
        classifier = create_classifier(settings().classifier_provider, settings().classifier_model)

        async def go():
            try:
                return await run(classifier, articles)
            finally:
                await classifier.aclose()

        rows, failed = asyncio.run(go())
        upsert_scores(engine(), rows)
        published = 0
        if rows and settings().redis_url:  # after the commit: the stream never runs ahead of the DB
            import redis

            from eventalpha.event_stream import article_feed_items, publish_alerts, publish_feed_items

            with redis.Redis.from_url(settings().redis_url, decode_responses=True) as r:
                publish_feed_items(r, article_feed_items(articles, rows))  # everything → web UI
                members = index_members().members
                eligible_symbols = set(members["sp500"]).union(members["nasdaq100"])
                published = publish_alerts(r, articles, rows, eligible_symbols=eligible_symbols)
        if rows and rows[0]["model"] != classifier.model_id:
            print(f"warning: requested {classifier.model_id}, provider answered as {rows[0]['model']}")
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
