"""Rate-limited HTTP client for SEC EDGAR.

SEC fair access: <= 10 requests/second across all your traffic, and a User-Agent with
contact info. https://www.sec.gov/os/accessing-edgar-data
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class RateLimitedClient:
    """Spaces requests evenly and retries SEC throttling / transient errors."""

    def __init__(self, user_agent: str, requests_per_second: float, timeout: float = 60.0) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._interval = 1.0 / requests_per_second
        self._next_at = 0.0

    def _wait(self) -> None:
        now = time.monotonic()
        if now < self._next_at:
            time.sleep(self._next_at - now)
        self._next_at = max(now, self._next_at) + self._interval

    @staticmethod
    def _backoff(status: int | str, url: str, attempt: int) -> None:
        delay = min(2**attempt, 30)
        log.warning("SEC %s on %s, retrying in %ss", status, url, delay)
        time.sleep(delay)

    def get(self, url: str, max_attempts: int = 4) -> httpx.Response:
        for attempt in range(1, max_attempts + 1):
            self._wait()
            try:
                resp = self._client.get(url)
            except httpx.TransportError as exc:  # timeouts, resets, DNS: as transient as a 503
                if attempt == max_attempts:
                    raise
                self._backoff(type(exc).__name__, url, attempt)
                continue
            if resp.status_code not in RETRY_STATUSES or attempt == max_attempts:
                return resp
            self._backoff(resp.status_code, url, attempt)
        raise AssertionError("unreachable")

    def stream_lines(self, url: str, max_attempts: int = 4) -> Iterator[str]:
        # Retry only before the first line is yielded; a failure mid-body propagates.
        for attempt in range(1, max_attempts + 1):
            self._wait()
            with self._client.stream("GET", url) as resp:
                if resp.status_code in RETRY_STATUSES and attempt < max_attempts:
                    self._backoff(resp.status_code, url, attempt)
                    continue
                resp.raise_for_status()
                yield from resp.iter_lines()
                return

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RateLimitedClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
