"""Baseline smoke tests, carried over from the pre-loop scaffold.

Assertions are unchanged from the baseline; only line wrapping and import
order were adjusted to satisfy Ruff.
"""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_login_success():
    response = client.post('/auth/login', json={'email': 'admin@northbridge.edu', 'password': 'demo-admin'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['role'] == 'administrator'
    assert payload['institution_id'] == 1


def test_login_fail():
    response = client.post('/auth/login', json={'email': 'admin@northbridge.edu', 'password': 'wrong-password'})
    assert response.status_code == 401


def test_cross_tenant_access_rejected():
    login = client.post('/auth/login', json={'email': 'student@northbridge.edu', 'password': 'demo-student'})
    token = login.json()['access_token']
    response = client.get('/institutions/2/rooms', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 403


def test_dashboard_overview_for_logged_in_user():
    login = client.post('/auth/login', json={'email': 'operator@northbridge.edu', 'password': 'demo-operator'})
    token = login.json()['access_token']
    response = client.get('/dashboard/overview', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    body = response.json()
    assert body['institution_id'] == 1
    assert body['rooms'] >= 1


def test_generate_schedule_returns_rows():
    login = client.post('/auth/login', json={'email': 'admin@northbridge.edu', 'password': 'demo-admin'})
    token = login.json()['access_token']
    response = client.post(
        '/schedules/generate',
        headers={'Authorization': f'Bearer {token}'},
        json={'institution_id': 1, 'campus_id': 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert 'schedule' in body
    assert isinstance(body['schedule'], list)


def test_ai_without_provider_returns_demo_message():
    login = client.post('/auth/login', json={'email': 'faculty@northbridge.edu', 'password': 'demo-faculty'})
    token = login.json()['access_token']
    response = client.post(
        '/ai/chat',
        headers={'Authorization': f'Bearer {token}'},
        json={'prompt': 'What classes do I have on Monday?'},
    )
    assert response.status_code == 200
    assert 'AI is not configured' in response.json()['answer']
