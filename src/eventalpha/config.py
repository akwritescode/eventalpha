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
    jev_model: str
    raw_data_dir: Path
    raw_bucket: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    healthchecks_ping_url: str | None
    redis_url: str | None
    sec_requests_per_second: float

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get(
                "EVENTALPHA_DATABASE_URL", "postgresql+psycopg://eventalpha:eventalpha@localhost:5433/eventalpha"
            ),
            # SEC fair-access policy requires a descriptive User-Agent with a contact address.
            sec_user_agent=_required("SEC_USER_AGENT"),
            # Pin a versioned model: thresholds tuned on one version don't transfer to the next.
            jev_model=os.environ.get("JEV_MODEL", "jev-1.14.0"),
            raw_data_dir=Path(os.environ.get("RAW_DATA_DIR", "data/raw")),
            # Set in production: raw landing goes to object storage instead of local disk.
            raw_bucket=_optional("RAW_BUCKET"),
            telegram_bot_token=_optional("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_optional("TELEGRAM_CHAT_ID"),
            healthchecks_ping_url=_optional("HEALTHCHECKS_PING_URL"),
            redis_url=_optional("REDIS_URL"),
            sec_requests_per_second=float(os.environ.get("SEC_REQUESTS_PER_SECOND", "4")),
        )
