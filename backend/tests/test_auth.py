"""Authentication: app-managed username/password and account state."""

from fastapi.testclient import TestClient


def test_login_with_username(client: TestClient):
    response = client.post('/auth/login', json={'username': 'admin', 'password': 'demo-admin'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['role'] == 'administrator'
    assert payload['institution_id'] == 1
    assert payload['username'] == 'admin'
    assert payload['full_name'] == 'Alice Admin'


def test_login_with_email_still_works(client: TestClient):
    response = client.post('/auth/login', json={'email': 'student@northbridge.edu', 'password': 'demo-student'})
    assert response.status_code == 200
    assert response.json()['role'] == 'student'


def test_login_wrong_password_rejected(client: TestClient):
    response = client.post('/auth/login', json={'username': 'admin', 'password': 'nope'})
    assert response.status_code == 401


def test_login_unknown_username_rejected(client: TestClient):
    response = client.post('/auth/login', json={'username': 'ghost', 'password': 'whatever'})
    assert response.status_code == 401


def test_login_requires_an_identifier(client: TestClient):
    response = client.post('/auth/login', json={'password': 'whatever'})
    assert response.status_code == 422


def test_me_requires_token(client: TestClient):
    assert client.get('/auth/me').status_code == 401


def test_me_rejects_garbage_token(client: TestClient):
    response = client.get('/auth/me', headers={'Authorization': 'Bearer not-a-jwt'})
    assert response.status_code == 401


def test_me_returns_profile(client: TestClient, student_headers: dict[str, str]):
    response = client.get('/auth/me', headers=student_headers)
    assert response.status_code == 200
    body = response.json()
    assert body['username'] == 'student'
    assert body['role'] == 'student'
    assert body['institution_id'] == 1
    assert body['institution_name'] == 'Northbridge University'
    assert body['student_group_id'] is not None
