"""S-02: the login throttle survives its store being recreated.

The defect class being pinned down: with the in-memory store, every process
(or uvicorn worker) counted only its own failures, so a deployment with N
replicas multiplied the effective lockout threshold N-fold and every restart
reset it. The store now lives in the ``loginattempt`` table, so a *fresh*
``LoginRateLimiter`` — the closest a unit test can get to a fresh process —
enforces exactly the failures recorded before it existed.

The sliding-window semantics, the identical unknown/known-account behaviour,
and the R-014 timing equalization are covered unchanged by
``tests/test_login_throttle.py`` (which runs against the same DB-backed
implementation) and by the dummy-hash verification in ``app/api/auth.py``,
which this change does not touch.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.db import engine
from app.models import LoginAttempt
from app.services.rate_limit import LoginRateLimiter, _utcnow, login_rate_limiter
from fastapi.testclient import TestClient
from sqlmodel import Session, select

KEY = ('testclient', 'student')


def _count_rows() -> int:
    with Session(engine) as session:
        return len(session.exec(select(LoginAttempt)).all())


def _record_failures(count: int, key: tuple[str, str] = KEY) -> None:
    with Session(engine) as session:
        for _ in range(count):
            login_rate_limiter.record_failure(session, key)


def test_lockout_survives_a_fresh_limiter_instance(client: TestClient):
    """Five failures lock the key; a brand-new limiter still enforces it."""
    _record_failures(5)

    fresh = LoginRateLimiter()  # no shared in-memory state with the original
    with Session(engine) as session:
        assert fresh.locked_for(session, KEY) > 0


def test_lockout_survives_a_fresh_limiter_through_the_http_endpoint(
    client: TestClient, monkeypatch
):
    """End to end: a fresh limiter (fresh process) still returns 429."""
    for _ in range(5):
        denied = client.post('/auth/login', json={'username': 'student', 'password': 'wrong-password'})
        assert denied.status_code == 401

    from app.api import auth as auth_module

    monkeypatch.setattr(auth_module, 'login_rate_limiter', LoginRateLimiter())
    blocked = client.post('/auth/login', json={'username': 'student', 'password': 'demo-student'})
    assert blocked.status_code == 429
    assert blocked.headers['retry-after'].isdigit()


def test_failures_are_shared_between_two_limiter_instances(client: TestClient):
    """Two simultaneous instances (two workers) count the same window."""
    worker_a = LoginRateLimiter()
    worker_b = LoginRateLimiter()
    with Session(engine) as session:
        for _ in range(4):
            worker_a.record_failure(session, KEY)
        # Worker B has never recorded anything itself, yet sees all four.
        assert len(worker_b._window(session, KEY, _utcnow())) == 4
        # One more failure through B locks the pair for both.
        worker_b.record_failure(session, KEY)
        assert worker_a.locked_for(session, KEY) > 0


def test_expired_attempts_are_pruned_and_do_not_count(client: TestClient):
    """Failures older than the window are deleted, not accumulated."""
    _record_failures(4)
    # Age the earliest failure past the 15-minute window.
    with Session(engine) as session:
        earliest = session.exec(
            select(LoginAttempt).where(LoginAttempt.identifier == KEY[1]).order_by(LoginAttempt.failed_at)
        ).first()
        earliest.failed_at = earliest.failed_at - timedelta(seconds=901)
        session.add(earliest)
        session.commit()

    with Session(engine) as session:
        assert login_rate_limiter.locked_for(session, KEY) == 0  # only 4 count

    # The next operation prunes the expired row globally.
    login_rate_limiter.record_failure(Session(engine), ('other-ip', 'other-user'))
    # 3 still-counted failures for KEY + the new one; the aged row is gone.
    assert _count_rows() == 4


def test_window_slide_unlocks_after_the_earliest_failure_expires(client: TestClient):
    """A full window of failures unlocks once the earliest slides out."""
    _record_failures(5)
    with Session(engine) as session:
        assert login_rate_limiter.locked_for(session, KEY) > 0
        earliest = session.exec(
            select(LoginAttempt).where(LoginAttempt.identifier == KEY[1]).order_by(LoginAttempt.failed_at)
        ).first()
        earliest.failed_at = earliest.failed_at - timedelta(seconds=901)
        session.add(earliest)
        session.commit()
        assert login_rate_limiter.locked_for(session, KEY) == 0


def test_success_deletes_the_recorded_failures(client: TestClient):
    """A correct password clears the pair's rows from the store."""
    _record_failures(3)
    login_rate_limiter.record_success(Session(engine), KEY)
    assert _count_rows() == 0
    with Session(engine) as session:
        assert login_rate_limiter.locked_for(session, KEY) == 0
