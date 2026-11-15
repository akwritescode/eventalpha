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


def send_telegram(settings: Settings, text: str, ops: bool = False) -> bool:
    """Channel messages (signals) by default; `ops=True` for pipeline alerts, which go to
    TELEGRAM_OPS_CHAT_ID only and are dropped (logged) when it isn't set: subscribers never
    see operational noise. Returns whether Telegram accepted the message."""
    chat_id = settings.telegram_ops_chat_id if ops else settings.telegram_chat_id
    if not (settings.telegram_bot_token and chat_id):
        if ops:
            log.warning("ops alert not sent (TELEGRAM_OPS_CHAT_ID unset): %s", text[:200])
        return False
    # Never log the exception or URL as is: the bot token is part of the URL.
    target = "ops chat" if ops else "channel"
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
    except httpx.HTTPError as exc:  # an alert failure must never fail the task itself
        log.warning("Telegram alert to %s failed: %s", target, type(exc).__name__)
        return False
    if resp.status_code != 200:
        try:
            reason = resp.json().get("description", "")
        except ValueError:
            reason = ""
        log.warning("Telegram alert to %s failed: HTTP %s %s", target, resp.status_code, reason)
        return False
    return True


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
    # None on some task instances: comparing it with >= would raise inside the failure
    # callback and hide the real failure.
    map_index = getattr(ti, "map_index", -1)
    return (
        f"🔴 <b>{html.escape(ti.dag_id)}</b> · {html.escape(ti.task_id)}"
        f"{f' [{map_index}]' if isinstance(map_index, int) and map_index >= 0 else ''}\n"
        f"run: <code>{html.escape(str(context.get('run_id')))}</code>\n"
        f"try {ti.try_number}: {html.escape(repr(exc)[:500]) if exc else 'failed'}"
    )
