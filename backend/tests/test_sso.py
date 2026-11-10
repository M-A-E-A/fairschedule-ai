"""Google/OIDC SSO: discovery, redirect, state validation, provisioning."""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.services import sso
from jose import jwt


@pytest.fixture
def sso_enabled(monkeypatch):
    """Point the shared Settings instance at a fake Google OAuth client."""
    settings = get_settings()
    monkeypatch.setattr(settings, 'sso_provider', 'google')
    monkeypatch.setattr(settings, 'google_client_id', 'test-client-id')
    monkeypatch.setattr(settings, 'google_client_secret', 'test-client-secret')
    return settings


def test_sso_config_reports_disabled_by_default(client):
    config = client.get('/auth/sso/config')
    assert config.status_code == 200
    body = config.json()
    assert body['enabled'] is False
    assert body['login_url'] == ''
    assert body['client_id'] == ''


def test_sso_config_reports_enabled_when_configured(client, sso_enabled):
    config = client.get('/auth/sso/config').json()
    assert config['enabled'] is True
    assert config['login_url'] == '/auth/sso/login'
    assert config['client_id'] == 'test-client-id'
    assert config['redirect_uri'].endswith('/auth/sso/callback')


def test_login_redirects_to_provider_with_state(client, sso_enabled):
    response = client.get('/auth/sso/login', follow_redirects=False)
    assert response.status_code == 302
    location = response.headers['location']
    assert location.startswith('https://accounts.google.com/')
    assert 'client_id=test-client-id' in location
    assert 'state=' in location
    assert 'response_type=code' in location


def test_callback_rejects_invalid_state(client, sso_enabled):
    response = client.get('/auth/sso/callback?code=abc&state=not-a-valid-state', follow_redirects=False)
    assert response.status_code == 400


def test_callback_rejects_missing_code(client, sso_enabled):
    state = sso.create_state_token(nonce='n')
    response = client.get(f'/auth/sso/callback?state={state}', follow_redirects=False)
    assert response.status_code == 422  # required query parameter missing


def test_callback_redirects_with_fragment_token(client, sso_enabled, monkeypatch):
    monkeypatch.setattr(
        sso, 'exchange_code_for_identity',
        lambda code: {'sub': 'google-sub-1', 'email': 'sso.user@northbridge.edu', 'name': 'SSO User'},
    )
    state = sso.create_state_token(nonce='n')
    response = client.get(
        f'/auth/sso/callback?code=auth-code&state={state}', follow_redirects=False
    )
    assert response.status_code == 302
    location = response.headers['location']
    assert '/login#access_token=' in location
    token = location.split('access_token=', 1)[1]
    me = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert me.status_code == 200
    assert me.json()['email'] == 'sso.user@northbridge.edu'


def test_new_identity_is_provisioned_as_student(client, sso_enabled, monkeypatch):
    monkeypatch.setattr(
        sso, 'exchange_code_for_identity',
        lambda code: {'sub': 'google-sub-new', 'email': 'brand.new@northbridge.edu', 'name': 'Brand New'},
    )
    state = sso.create_state_token(nonce='n')
    response = client.get(
        f'/auth/sso/callback?code=auth-code&state={state}', follow_redirects=False
    )
    assert response.status_code == 302
    token = response.headers['location'].split('access_token=', 1)[1]
    me = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'}).json()
    assert me['role'] == 'student'
    assert me['institution_id'] == 1
    assert me['username'] == 'brand.new'
    # Password login is impossible for an SSO-only account.
    login = client.post('/auth/login', json={'username': 'brand.new', 'password': 'whatever'})
    assert login.status_code == 401


def test_existing_account_is_linked_not_duplicated(client, sso_enabled, monkeypatch):
    monkeypatch.setattr(
        sso, 'exchange_code_for_identity',
        lambda code: {'sub': 'google-sub-admin', 'email': 'admin@northbridge.edu', 'name': 'Alice Admin'},
    )
    state = sso.create_state_token(nonce='n')
    response = client.get(
        f'/auth/sso/callback?code=auth-code&state={state}', follow_redirects=False
    )
    assert response.status_code == 302
    token = response.headers['location'].split('access_token=', 1)[1]
    me = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'}).json()
    assert me['role'] == 'administrator'
    assert me['institution_id'] == 1


def test_provisioning_is_audited(client, sso_enabled, monkeypatch):
    monkeypatch.setattr(
        sso, 'exchange_code_for_identity',
        lambda code: {'sub': 'google-sub-audited', 'email': 'audited@northbridge.edu', 'name': 'Audited'},
    )
    state = sso.create_state_token(nonce='n')
    client.get(f'/auth/sso/callback?code=auth-code&state={state}', follow_redirects=False)

    admin_login = client.post('/auth/login', json={'username': 'admin', 'password': 'demo-admin'})
    admin = {'Authorization': f"Bearer {admin_login.json()['access_token']}"}
    events = client.get('/auth/me', headers=admin)
    assert events.status_code == 200
    # Audit trail is admin-only, and the provisioning event exists.
    audit = client.get('/audit-events', headers=admin).json()
    assert any(event['event_type'] == 'sso_provisioned' for event in audit)


def test_provider_exchange_failure_is_502(client, sso_enabled, monkeypatch):
    def _boom(code):
        raise sso.httpx.HTTPError('provider down')

    monkeypatch.setattr(sso, 'exchange_code_for_identity', _boom)
    state = sso.create_state_token(nonce='n')
    response = client.get(f'/auth/sso/callback?code=auth-code&state={state}', follow_redirects=False)
    assert response.status_code == 502


def test_state_tokens_are_signed_and_scoped(sso_enabled):
    token = sso.create_state_token(nonce='abc')
    assert sso.verify_state_token(token) == 'abc'
    # A token signed for a different purpose is rejected even with our secret.
    forged = jwt.encode({'purpose': 'other', 'nonce': 'x'}, get_settings().jwt_secret, algorithm='HS256')
    with pytest.raises(ValueError):
        sso.verify_state_token(forged)
