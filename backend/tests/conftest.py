"""Shared test fixtures.

The environment is pinned to a dedicated SQLite database *before* the app is
imported, so tests never touch a developer's demo database. The schema always
comes from ``alembic upgrade head``, which is exactly what production runs:
the conftest applies it once at import time (so auth-infrastructure tables
exist even for tests that never boot the app's lifespan) and the app's
lifespan re-applies it as a no-op.

An explicit ``DATABASE_URL`` environment variable is respected instead of the
SQLite default — this is how the CI PostgreSQL job points the same suite at
a real ``postgres:16`` service (S-03). With no ``DATABASE_URL`` set, the
local default stays exactly as before: a throwaway SQLite file.
"""

from __future__ import annotations

import os
import pathlib

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
_TEST_DB = _BACKEND_DIR / 'fairschedule_test.db'

if 'DATABASE_URL' not in os.environ:
    os.environ['DATABASE_URL'] = 'sqlite:///./fairschedule_test.db'
os.environ.setdefault('APP_ENV', 'test')
os.environ.setdefault('JWT_SECRET', 'test-only-secret-do-not-use-in-production')

if os.environ['DATABASE_URL'].startswith('sqlite') and _TEST_DB.exists():
    # Fresh file per run: schema changes always come from a fresh
    # ``alembic upgrade head``. (Only meaningful for the SQLite default;
    # a PostgreSQL URL owns its own lifecycle in CI.)
    _TEST_DB.unlink()

import pytest  # noqa: E402
from app.core.db import engine  # noqa: E402
from app.core.migrations import run_migrations  # noqa: E402
from app.main import app  # noqa: E402
from app.services.rate_limit import login_rate_limiter  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

# Apply the migration chain once, before any test or fixture can touch the
# database. The app lifespan's own run_migrations() is then a no-op upgrade.
run_migrations()


@pytest.fixture(autouse=True)
def _fresh_login_throttle():
    """Start every test with an empty login-failure store.

    The throttle state lives in the database (S-02), shared by the whole
    test session; without this reset, failures recorded in one test could
    lock an account out in a later, unrelated test. Tests that exercise the
    lockout itself build up their own counts inside their own body.
    """
    with Session(engine) as session:
        login_rate_limiter.reset(session)
    yield
    with Session(engine) as session:
        login_rate_limiter.reset(session)


@pytest.fixture(scope='session')
def lifespan_client() -> TestClient:
    """Run the app lifespan (Alembic migrations + demo seed) exactly once."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope='module')
def module_login():
    """Module-scoped token helper: cheap, but scoped so tests stay isolated.

    Signature is ``module_login(client, username, password=None)`` to match
    how every test module calls it.
    """
    def _login(client: TestClient, username: str, password: str | None = None) -> dict[str, str]:
        return auth_headers(client, username, password or f'demo-{username}')
    return _login


@pytest.fixture(scope='session')
def client(lifespan_client: TestClient) -> TestClient:
    return lifespan_client


def login(client: TestClient, username: str, password: str) -> str:
    """Return a bearer token for the given credentials."""
    response = client.post('/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200, response.text
    return response.json()['access_token']


def auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {login(client, username, password)}'}


@pytest.fixture(scope='session')
def admin_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'admin', 'demo-admin')


@pytest.fixture(scope='session')
def operator_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'operator', 'demo-operator')


@pytest.fixture(scope='session')
def faculty_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'faculty', 'demo-faculty')


@pytest.fixture(scope='session')
def student_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'student', 'demo-student')


@pytest.fixture(scope='session')
def harbor_admin_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, 'harbor-admin', 'demo-admin-harbor')
