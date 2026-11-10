"""In-memory failure throttling for the password login endpoint.

``POST /auth/login`` is the one endpoint that accepts unauthenticated
guessing, so it is the one endpoint with brute-force protection: a sliding
window of failed attempts per (client IP, account identifier). Once an
account/IP pair accumulates ``max_failures`` failures inside
``window_seconds``, further attempts for that pair are rejected with 429
until the window slides past the earliest counted failure.

Unknown usernames are throttled exactly like known ones (the key is the
identifier the client *attempted*, not one that must resolve), so the
lockout behaviour itself cannot distinguish existing accounts from
nonexistent ones.

The store is per-process memory, which is the right scope for this
application: it is single-worker by design (SQLite), and the counter only
needs to slow an attacker down, not survive restarts. Multi-worker
deployments would move this store to shared infrastructure (Redis, the
database) — that is documented here so the limitation is a decision, not
an accident.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict

ThrottleKey = tuple[str, str]

MAX_FAILURES = 5
WINDOW_SECONDS = 900.0


class LoginRateLimiter:
    """Sliding-window failure counter, keyed by (client IP, account)."""

    def __init__(self, max_failures: int = MAX_FAILURES, window_seconds: float = WINDOW_SECONDS) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[ThrottleKey, list[float]] = defaultdict(list)

    def _prune(self, key: ThrottleKey, now: float) -> list[float]:
        """Drop counted failures that have slid out of the window."""
        bucket = self._failures[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.pop(0)
        return bucket

    def record_failure(self, key: ThrottleKey) -> None:
        now = time.monotonic()
        self._prune(key, now)
        self._failures[key].append(now)

    def record_success(self, key: ThrottleKey) -> None:
        """Forget past failures once the right password is supplied."""
        self._failures.pop(key, None)

    def locked_for(self, key: ThrottleKey) -> int:
        """Seconds until the key unlocks; 0 when it is not locked."""
        bucket = self._prune(key, time.monotonic())
        if len(bucket) < self.max_failures:
            return 0
        elapsed = time.monotonic() - bucket[0]
        return max(1, math.ceil(self.window_seconds - elapsed))

    def reset(self) -> None:
        """Clear all counted failures (test isolation)."""
        self._failures.clear()


login_rate_limiter = LoginRateLimiter()

__all__ = ['LoginRateLimiter', 'login_rate_limiter']
