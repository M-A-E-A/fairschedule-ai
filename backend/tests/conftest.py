"""Shared test fixtures.

The environment is pinned to a dedicated SQLite database *before* the app is
imported, so tests never touch a developer's demo database. The file is
deleted on every session start: schema changes always come from a fresh
``alembic upgrade head``, which is exactly what production runs.
"""

from __future__ import annotations

import os
import pathlib

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
_TEST_DB = _BACKEND_DIR / 'fairschedule_test.db'

os.environ['DATABASE_URL'] = 'sqlite:///./fairschedule_test.db'
os.environ.setdefault('APP_ENV', 'test')
os.environ.setdefault('JWT_SECRET', 'test-only-secret-do-not-use-in-production')

if _TEST_DB.exists():
    _TEST_DB.unlink()

import pytest  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


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
