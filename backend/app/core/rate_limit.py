"""In-process rate limiting for authentication endpoints.

Scope and honesty
-----------------
This is a **single-process** limiter backed by an in-memory sliding window. It
raises the cost of online password guessing against one instance. It is *not* a
distributed limiter: with several API replicas each holds its own counters, so
the effective limit is `configured_limit x replica_count`.

Serious abuse protection belongs at the edge (reverse proxy, WAF, or a shared
Redis counter). This exists so a single deployment is not defenceless, and so
the configured `RS_LOGIN_RATE_LIMIT_PER_MINUTE` value actually does something
rather than being decorative.

Counting is keyed on client IP *and* the submitted email, so one attacker
cannot lock out a legitimate user by hammering their address from elsewhere:
the attacker's own IP bucket fills first.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.errors import RateLimitError
from app.core.logging import get_logger

logger = get_logger(__name__)

WINDOW_SECONDS = 60
# Stop unbounded growth if a host is sprayed with unique keys.
MAX_TRACKED_KEYS = 10_000


class SlidingWindowLimiter:
    """Fixed-duration sliding window over request timestamps."""

    def __init__(self, *, limit: int, window_seconds: int = WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()
        return hits

    def check(self, key: str) -> None:
        """Record an attempt; raise :class:`RateLimitError` if over the limit."""
        if self.limit <= 0:  # 0 or negative disables limiting
            return

        now = time.monotonic()
        with self._lock:
            if len(self._hits) > MAX_TRACKED_KEYS:
                self._evict_expired(now)

            hits = self._prune(key, now)
            if len(hits) >= self.limit:
                retry_after = int(self.window_seconds - (now - hits[0])) + 1
                logger.warning("Rate limit reached for key hash=%s", hash(key))
                raise RateLimitError(
                    f"Too many attempts. Please wait {retry_after} seconds and try again.",
                    details={"retry_after_seconds": retry_after},
                )
            hits.append(now)

    def _evict_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        for key in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
            del self._hits[key]

    def reset(self, key: str | None = None) -> None:
        """Clear counters — used after a successful login, and by tests."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


login_limiter = SlidingWindowLimiter(limit=settings.login_rate_limit_per_minute)


def login_key(ip_address: str | None, email: str) -> str:
    return f"{ip_address or 'unknown'}|{email.strip().lower()}"
