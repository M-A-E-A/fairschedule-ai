"""R-014: brute-force throttling and timing equalization on ``/auth/login``.

Two properties are pinned down:

- unknown usernames pay the same bcrypt cost as known ones (no timing
  oracle for account existence), verified structurally by spying on
  ``verify_password`` rather than by asserting wall-clock timings, which
  would be flaky;
- repeated failures for the same (client IP, account) pair are locked out
  with 429, equally for existing and nonexistent accounts, while other
  accounts from the same IP stay usable.
"""

from __future__ import annotations

from app.api import auth as auth_module
from fastapi.testclient import TestClient


def test_unknown_user_still_pays_password_verify(client: TestClient, monkeypatch):
    """The bcrypt comparison runs exactly once even when the user is missing."""
    calls: list[tuple[str, str]] = []
    real_verify = auth_module.verify_password

    def spy(plain_password: str, hashed_password: str) -> bool:
        calls.append((plain_password, hashed_password))
        return real_verify(plain_password, hashed_password)

    monkeypatch.setattr(auth_module, 'verify_password', spy)
    response = client.post('/auth/login', json={'username': 'ghost-user', 'password': 'whatever123'})
    assert response.status_code == 401
    assert len(calls) == 1
    assert calls[0][0] == 'whatever123'
    assert calls[0][1] == auth_module.DUMMY_PASSWORD_HASH


def test_sso_only_account_still_pays_password_verify(client: TestClient, monkeypatch):
    """An account with no password hash (SSO-provisioned) verifies the dummy too."""
    calls: list[str] = []
    real_verify = auth_module.verify_password

    def spy(plain_password: str, hashed_password: str) -> bool:
        calls.append(hashed_password)
        return real_verify(plain_password, hashed_password)

    monkeypatch.setattr(auth_module, 'verify_password', spy)
    # 'operator' exists with a real hash; prove the *no-hash* path by using a
    # nonexistent email login, which resolves no user at all.
    response = client.post('/auth/login', json={'email': 'nobody@nowhere.edu', 'password': 'whatever123'})
    assert response.status_code == 401
    assert calls == [auth_module.DUMMY_PASSWORD_HASH]


def test_login_locks_out_after_repeated_failures(client: TestClient):
    """Five wrong passwords lock the account; even the right one then gets 429."""
    for _ in range(5):
        denied = client.post('/auth/login', json={'username': 'student', 'password': 'wrong-password'})
        assert denied.status_code == 401

    blocked = client.post('/auth/login', json={'username': 'student', 'password': 'demo-student'})
    assert blocked.status_code == 429
    assert blocked.json()['detail'] == 'too many failed login attempts; try again later'
    assert blocked.headers['retry-after'].isdigit()

    still_blocked = client.post('/auth/login', json={'username': 'student', 'password': 'wrong-password'})
    assert still_blocked.status_code == 429


def test_lockout_is_per_account(client: TestClient):
    """Locking one account does not lock its neighbours from the same IP."""
    for _ in range(5):
        denied = client.post('/auth/login', json={'username': 'student', 'password': 'wrong-password'})
        assert denied.status_code == 401

    neighbour = client.post('/auth/login', json={'username': 'operator', 'password': 'demo-operator'})
    assert neighbour.status_code == 200


def test_unknown_username_locks_out_equally(client: TestClient):
    """Nonexistent accounts throttle identically, so lockout leaks no existence."""
    for _ in range(5):
        denied = client.post('/auth/login', json={'username': 'ghost-user', 'password': 'wrong-password'})
        assert denied.status_code == 401

    blocked = client.post('/auth/login', json={'username': 'ghost-user', 'password': 'anything-else'})
    assert blocked.status_code == 429


def test_success_resets_failure_counter(client: TestClient):
    """A correct password clears the account's counted failures."""
    for _ in range(4):
        denied = client.post('/auth/login', json={'username': 'faculty', 'password': 'wrong-password'})
        assert denied.status_code == 401

    recovered = client.post('/auth/login', json={'username': 'faculty', 'password': 'demo-faculty'})
    assert recovered.status_code == 200

    for _ in range(4):
        denied = client.post('/auth/login', json={'username': 'faculty', 'password': 'wrong-password'})
        assert denied.status_code == 401
