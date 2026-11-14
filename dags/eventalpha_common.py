"""Shared bits for the DAGs. Airflow puts the dags/ folder on sys.path, so DAG files
import this directly. Business logic lives in the eventalpha package; DAG files
only wire it together."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from functools import cache
from typing import TYPE_CHECKING

from airflow.sdk import Asset

from eventalpha.config import Settings

if TYPE_CHECKING:
    from sqlalchemy import Engine

DB_CONN_ID = "eventalpha_db"

# Assets give data-aware scheduling: classification runs when articles land,
# not at a guessed time. The URI doubles as lineage metadata.


def table_asset(table: str) -> Asset:
    # Name-only on purpose: an Asset with a URI makes Airflow load every installed provider's
    # URI handlers (Amazon, Google, ...) at parse time, ~6 s per task start on a laptop.
    return Asset(f"eventalpha.{table}")


ARTICLES = table_asset("articles")
ARTICLE_SCORES = table_asset("article_scores")
TICKER_UNIVERSE = table_asset("ticker_universe")
FAMILY_ASSETS = {
    "events": [ARTICLES],
    "insider": [table_asset("insider_transactions")],
    "holdings": [table_asset("institutional_holdings")],
    "periodic": [table_asset("report_sections"), table_asset("financial_facts")],
}


@cache
def settings() -> Settings:
    return Settings.from_env()


@cache
def engine() -> Engine:
    """Built from the Airflow connection, so tasks and SQL check operators share one config."""
    from airflow.sdk import Connection

    from eventalpha.db import make_engine  # SQLAlchemy loads only when a task needs the DB

    conn = Connection.get(DB_CONN_ID)
    url = f"postgresql+psycopg://{conn.login}:{conn.password}@{conn.host}:{conn.port or 5432}/{conn.schema}"
    return make_engine(url)


def chunk[T](items: Sequence[T], size: int) -> list[list[T]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def notify_failure(context) -> None:
    """on_failure_callback: fires after the last retry, so one alert per real failure."""
    from eventalpha.alerts import format_task_failure, send_telegram

    send_telegram(settings(), format_task_failure(context))


# Shared by every DAG: retries with backoff, then a Telegram alert.
DEFAULT_ARGS = {
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "on_failure_callback": notify_failure,
}
