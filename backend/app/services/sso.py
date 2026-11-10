"""Google OAuth / OIDC single sign-on flow.

The flow: ``GET /auth/sso/login`` redirects to the provider's authorization
endpoint with a signed ``state`` token; the provider redirects back to
``GET /auth/sso/callback`` with an authorization code; this module exchanges
that code for tokens and fetches the user's identity claims.

``exchange_code_for_identity`` performs the outbound HTTP calls and is
monkeypatched in tests so no test ever touches the network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from jose import JWTError, jwt

from app.core.config import get_settings

STATE_PURPOSE = 'sso_state'
STATE_EXPIRE_MINUTES = 10


def sso_enabled() -> bool:
    settings = get_settings()
    if settings.sso_provider not in ('google', 'oidc'):
        return False
    return bool(settings.google_client_id and settings.google_client_secret)


def redirect_uri() -> str:
    settings = get_settings()
    return settings.public_base_url.rstrip('/') + settings.sso_redirect_path


def frontend_login_url(fragment: str) -> str:
    settings = get_settings()
    return f"{settings.frontend_url.rstrip('/')}/login#{fragment}"


def create_state_token(nonce: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        'purpose': STATE_PURPOSE,
        'nonce': nonce,
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(minutes=STATE_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm='HS256')


def verify_state_token(state: str) -> str:
    """Return the nonce, raising ValueError when the state is not ours."""
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=['HS256'])
    except JWTError as exc:
        raise ValueError('invalid sso state') from exc
    if payload.get('purpose') != STATE_PURPOSE:
        raise ValueError('invalid sso state purpose')
    return str(payload.get('nonce', ''))


def build_authorize_url(state: str) -> str:
    settings = get_settings()
    params = httpx.QueryParams({
        'client_id': settings.google_client_id,
        'redirect_uri': redirect_uri(),
        'response_type': 'code',
        'scope': settings.oidc_scopes,
        'state': state,
        'access_type': 'offline',
        'prompt': 'select_account',
    })
    return f'{settings.oidc_authorize_url}?{params}'


def exchange_code_for_identity(code: str) -> dict:
    """Exchange the authorization code and return ``{'sub', 'email', 'name'}``.

    Raises ``httpx.HTTPError`` on any provider failure; callers translate that
    into an API error. Tests monkeypatch this function.
    """
    settings = get_settings()
    token_response = httpx.post(
        settings.oidc_token_url,
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri(),
            'client_id': settings.google_client_id,
            'client_secret': settings.google_client_secret,
        },
        timeout=15.0,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get('access_token')
    if not access_token:
        raise ValueError('provider returned no access token')
    userinfo_response = httpx.get(
        settings.oidc_userinfo_url,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=15.0,
    )
    userinfo_response.raise_for_status()
    claims = userinfo_response.json()
    email = claims.get('email')
    if not email:
        raise ValueError('provider returned no email claim')
    return {'sub': str(claims.get('sub', '')), 'email': email, 'name': claims.get('name') or email}
