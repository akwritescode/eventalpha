"""Operational alerts: Telegram for failures, healthchecks.io as a dead-man's switch.

Both are optional: with no token / URL configured (local dev) they do nothing.
"""

from __future__ import annotations

import html
import logging
from typing import Any

import httpx

from eventalpha.config import Settings

log = logging.getLogger(__name__)


def send_telegram(settings: Settings, text: str) -> None:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=10,
        ).raise_for_status()
    except httpx.HTTPError as exc:  # an alert failure must never fail the task itself
        log.warning("Telegram alert failed: %s", exc)


def ping_healthcheck(settings: Settings, suffix: str = "") -> None:
    """suffix "" = success, "/fail" = failure, "/start" = run started."""
    if not settings.healthchecks_ping_url:
        return
    try:
        httpx.get(settings.healthchecks_ping_url.rstrip("/") + suffix, timeout=10)
    except httpx.HTTPError as exc:
        log.warning("healthchecks ping failed: %s", exc)


def format_task_failure(context: dict[str, Any]) -> str:
    ti = context["task_instance"]
    exc = context.get("exception")
    return (
        f"🔴 <b>{html.escape(ti.dag_id)}</b> · {html.escape(ti.task_id)}"
        f"{f' [{ti.map_index}]' if getattr(ti, 'map_index', -1) >= 0 else ''}\n"
        f"run: <code>{html.escape(str(context.get('run_id')))}</code>\n"
        f"try {ti.try_number}: {html.escape(repr(exc)[:500]) if exc else 'failed'}"
    )
