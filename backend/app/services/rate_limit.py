"""Persistent failure throttling for the password login endpoint.

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

The store is the application database (``loginattempt`` table, S-02), not
process memory: multiple uvicorn workers or replicas each kept their own
counter with the in-memory implementation, multiplying the effective lockout
threshold per replica and resetting it on every restart. Every operation
commits its own transaction, because a failed login raises an HTTPException
after the failure is recorded — an uncommitted row would be rolled back when
the request session closes, silently dropping the count.

Wall-clock (``time.time``-based) timestamps are deliberate: a monotonic
clock resets with each process, which would break exactly the property the
persistent store exists for.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from app.models import LoginAttempt
from sqlmodel import Session, delete, select

ThrottleKey = tuple[str, str]

MAX_FAILURES = 5
WINDOW_SECONDS = 900.0


def _utcnow() -> datetime:
    """Naive UTC timestamp (naive so it round-trips identically on SQLite)."""
    return datetime.now(UTC).replace(tzinfo=None)


class LoginRateLimiter:
    """Sliding-window failure counter, keyed by (client IP, account).

    All state lives in the ``loginattempt`` table, shared by every worker of
    the deployment; the instance itself is stateless, so a freshly
    constructed limiter enforces exactly the failures recorded before it
    existed (the property S-02's tests pin down).
    """

    def __init__(self, max_failures: int = MAX_FAILURES, window_seconds: float = WINDOW_SECONDS) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds

    def _prune(self, session: Session, now: datetime) -> None:
        """Drop counted failures that have slid out of the window.

        Global (not per-key): expired rows for keys that never log in again
        must not accumulate forever, and the table cannot grow unboundedly.
        """
        cutoff = now - timedelta(seconds=self.window_seconds)
        session.exec(delete(LoginAttempt).where(LoginAttempt.failed_at <= cutoff))
        session.commit()

    def _window(self, session: Session, key: ThrottleKey, now: datetime) -> list[LoginAttempt]:
        """Counted failures for ``key`` inside the window, oldest first."""
        cutoff = now - timedelta(seconds=self.window_seconds)
        statement = (
            select(LoginAttempt)
            .where(LoginAttempt.client_ip == key[0], LoginAttempt.identifier == key[1])
            .where(LoginAttempt.failed_at > cutoff)
            .order_by(LoginAttempt.failed_at)
        )
        return list(session.exec(statement).all())

    def record_failure(self, session: Session, key: ThrottleKey) -> None:
        now = _utcnow()
        self._prune(session, now)
        session.add(LoginAttempt(client_ip=key[0], identifier=key[1], failed_at=now))
        session.commit()

    def record_success(self, session: Session, key: ThrottleKey) -> None:
        """Forget past failures once the right password is supplied."""
        session.exec(
            delete(LoginAttempt).where(LoginAttempt.client_ip == key[0], LoginAttempt.identifier == key[1])
        )
        session.commit()

    def locked_for(self, session: Session, key: ThrottleKey) -> int:
        """Seconds until the key unlocks; 0 when it is not locked."""
        now = _utcnow()
        self._prune(session, now)
        window = self._window(session, key, now)
        if len(window) < self.max_failures:
            return 0
        earliest = window[0].failed_at
        elapsed = (now - earliest).total_seconds()
        return max(1, math.ceil(self.window_seconds - elapsed))

    def reset(self, session: Session) -> None:
        """Clear all counted failures (test isolation)."""
        session.exec(delete(LoginAttempt))
        session.commit()


login_rate_limiter = LoginRateLimiter()


__all__ = ['LoginRateLimiter', 'login_rate_limiter']
