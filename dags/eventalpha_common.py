"""Shared bits for the DAGs. Airflow puts the dags/ folder on sys.path, so DAG files
import this directly. Business logic lives in the eventalpha package; DAG files
only wire it together."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from functools import cache
from typing import TYPE_CHECKING

import pendulum
from airflow.sdk import Asset

from eventalpha.config import Settings

if TYPE_CHECKING:
    from sqlalchemy import Engine

DB_CONN_ID = "eventalpha_db"

# Schedules are written in New York time: SEC filing dates, the evening index and the trading
# day are all Eastern. Airflow keeps "0 1 * * *" at 01:00 ET across daylight saving changes
# (a UTC cron would drift to 02:00 ET every summer). Storage and run IDs stay UTC.
NY = pendulum.timezone("America/New_York")
START_DATE = pendulum.datetime(2026, 11, 1, tz=NY)

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

    send_telegram(settings(), format_task_failure(context), ops=True)


# Shared by every DAG: retries with backoff, then a Telegram alert.
DEFAULT_ARGS = {
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "on_failure_callback": notify_failure,
}


@cache
def market_data():
    from eventalpha.marketdata import create_market_data

    return create_market_data(settings())


@cache
def universe():
    import os
    from pathlib import Path

    from eventalpha.signals.universe import load_universe

    return load_universe(Path(os.environ.get("UNIVERSE_CONFIG", "/opt/airflow/project/config/spx_universe.yaml")))


def index_members_path():
    """config/index_members.json, next to the SPX universe file."""
    import os
    from pathlib import Path

    config = Path(os.environ.get("UNIVERSE_CONFIG", "/opt/airflow/project/config/spx_universe.yaml")).parent
    return config / "index_members.json"


def index_members():
    """S&P 500, Nasdaq-100 and Dow 30 members from the reviewed snapshot (not cached: a
    long-lived worker must see a merged rebalance without a restart)."""
    from eventalpha.index_members import load_snapshot

    return load_snapshot(index_members_path())


@cache
def company_matcher():
    """Company names → tickers for news items (SEC ticker list + config/company_aliases.yaml)."""
    import os
    from pathlib import Path

    from eventalpha.companies import CompanyMatcher

    config = Path(os.environ.get("UNIVERSE_CONFIG", "/opt/airflow/project/config/spx_universe.yaml")).parent
    return CompanyMatcher.from_db(engine(), config / "company_aliases.yaml")


def scheduled_local_time(context) -> pendulum.DateTime:
    """When this run is "for", in New York time: params.as_of on a manual replay, otherwise the
    time it was scheduled for."""
    as_of = (context.get("params") or {}).get("as_of")
    if as_of:
        return pendulum.parse(as_of).in_timezone(NY)
    return pendulum.instance(context["dag_run"].run_after).in_timezone(NY)


def trading_session_gate(context, close_offset: timedelta | None = None) -> bool:
    """Should this run fire? Market must be open today. With `close_offset`, the run must also be
    the one scheduled at today's close + offset (DAGs schedule both the normal and the early-close
    time; only one passes). Manual runs with params.force=true skip the time check."""
    from eventalpha.sessions import close_relative_due, get_session, refresh_sessions

    when = scheduled_local_time(context)
    session = get_session(engine(), when.date())
    if session is None:  # calendar not loaded yet for this month
        refresh_sessions(engine(), market_data(), when.date())
        session = get_session(engine(), when.date())
    if session is None or not session.is_open:
        print(f"{when.date()} is not a trading day ({session and session.description})")
        return False
    if close_offset is None or context["params"].get("force") or context["params"].get("as_of"):
        return True  # manual run or replay: skip the "is this the run that's due" check
    due = close_relative_due(session, when.time().replace(second=0, microsecond=0), close_offset)
    print(f"session closes {session.close_time}; run at {when:%H:%M} {'is' if due else 'is not'} the one due")
    return due
