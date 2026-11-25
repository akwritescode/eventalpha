"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required (see .env.example)")
    return value


def _optional(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


@dataclass(frozen=True)
class Settings:
    database_url: str
    sec_user_agent: str
    classifier_provider: str
    classifier_model: str | None
    raw_data_dir: Path
    raw_bucket: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    telegram_ops_chat_id: str | None
    healthchecks_ping_url: str | None
    redis_url: str | None
    market_data_provider: str
    tradier_broker_key: str | None
    fred_api_key: str | None
    bls_api_key: str | None
    sec_requests_per_second: float
    # Prepended to every Telegram message, e.g. "[local]" from docker-compose.override.yml, so
    # alerts from a dev stack sharing the production bot are recognisable. Empty in production.
    alert_prefix: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get(
                "EVENTALPHA_DATABASE_URL", "postgresql+psycopg://eventalpha:eventalpha@localhost:5433/eventalpha"
            ),
            # SEC fair-access policy requires a descriptive User-Agent with a contact address.
            sec_user_agent=_required("SEC_USER_AGENT"),
            # Which classifier provider scores articles, and which of its models (None = the
            # provider's pinned default). See eventalpha/classification/providers/.
            classifier_provider=os.environ.get("CLASSIFIER_PROVIDER", "typesafe"),
            classifier_model=_optional("CLASSIFIER_MODEL"),
            raw_data_dir=Path(os.environ.get("RAW_DATA_DIR", "data/raw")),
            # Set in production: raw landing goes to object storage instead of local disk.
            raw_bucket=_optional("RAW_BUCKET"),
            telegram_bot_token=_optional("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_optional("TELEGRAM_CHAT_ID"),  # the public alerts channel
            telegram_ops_chat_id=_optional("TELEGRAM_OPS_CHAT_ID"),  # pipeline failures; never the channel
            healthchecks_ping_url=_optional("HEALTHCHECKS_PING_URL"),
            redis_url=_optional("REDIS_URL"),
            market_data_provider=os.environ.get("MARKET_DATA_PROVIDER", "tradier"),
            tradier_broker_key=_optional("TRADIER_BROKER_KEY"),
            fred_api_key=_optional("FRED_API_KEY"),
            bls_api_key=_optional("BLS_API_KEY"),
            sec_requests_per_second=float(os.environ.get("SEC_REQUESTS_PER_SECOND", "4")),
            alert_prefix=_optional("ALERT_PREFIX"),
        )
