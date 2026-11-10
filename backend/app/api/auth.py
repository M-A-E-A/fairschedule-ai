"""Authentication endpoints: username/password login and Google/OIDC SSO."""

from __future__ import annotations

import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.roles import ALL_ROLES
from app.core.security import DUMMY_PASSWORD_HASH, create_access_token, verify_password
from app.models import AuditEvent, Institution, User
from app.schemas.auth import AuthToken, LoginRequest, MeResponse, SsoConfigResponse
from app.services import sso
from app.services.rate_limit import login_rate_limiter

router = APIRouter(prefix='/auth', tags=['auth'])
settings = get_settings()


def _issue_token(user: User) -> AuthToken:
    token = create_access_token(user.id, user.role, user.institution_id)
    return AuthToken(
        access_token=token,
        role=user.role,
        institution_id=user.institution_id,
        username=user.username,
        full_name=user.full_name,
    )


@router.post('/login', response_model=AuthToken)
def login(payload: LoginRequest, request: Request, session: Session = Depends(get_session)) -> AuthToken:
    """Sign in with the app-managed username (or the account's email).

    Two hardening properties hold for every 401:

    - The bcrypt verification runs exactly once whether or not the account
      exists (against ``DUMMY_PASSWORD_HASH`` when there is no stored hash),
      so response timing never reveals which usernames/emails are real.
    - Failures are counted per (client IP, attempted identifier); past the
      threshold the pair is locked out with 429 regardless of whether the
      account exists, so the throttling itself leaks nothing either.
    """
    client_ip = request.client.host if request.client else 'unknown'
    throttle_key = (client_ip, (payload.username or str(payload.email)).lower())
    wait_seconds = login_rate_limiter.locked_for(throttle_key)
    if wait_seconds > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail='too many failed login attempts; try again later',
            headers={'Retry-After': str(wait_seconds)},
        )

    statement = select(User).where(User.username == payload.username) if payload.username else select(User).where(
        User.email == (payload.email or '').lower()
    )
    user = session.exec(statement).first()
    stored_hash = user.password_hash if user is not None and user.password_hash else DUMMY_PASSWORD_HASH
    password_ok = verify_password(payload.password, stored_hash)
    if user is None or not user.password_hash or not password_ok:
        login_rate_limiter.record_failure(throttle_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid credentials')
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='account disabled')
    login_rate_limiter.record_success(throttle_key)
    return _issue_token(user)


@router.get('/me', response_model=MeResponse)
def me(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> MeResponse:
    institution = session.get(Institution, current_user.institution_id)
    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        institution_id=current_user.institution_id,
        institution_name=institution.name if institution else '',
        student_group_id=current_user.student_group_id,
        lecturer_id=current_user.lecturer_id,
    )


def _sso_config_payload() -> dict[str, Any]:
    enabled = sso.sso_enabled()
    return {
        'enabled': enabled,
        'provider': settings.sso_provider if enabled else 'none',
        'login_url': '/auth/sso/login' if enabled else '',
        'client_id': settings.google_client_id if enabled else '',
        'redirect_uri': sso.redirect_uri() if enabled else '',
    }


@router.get('/sso/config', response_model=SsoConfigResponse)
def sso_config() -> SsoConfigResponse:
    return SsoConfigResponse(**_sso_config_payload())


@router.get('/sso/login')
def sso_login() -> RedirectResponse:
    """Redirect the browser to the identity provider's consent screen."""
    if not sso.sso_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='sso is not configured')
    state = sso.create_state_token(nonce=secrets.token_urlsafe(16))
    return RedirectResponse(sso.build_authorize_url(state), status_code=status.HTTP_302_FOUND)


@router.get('/sso/callback')
def sso_callback(
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Handle the provider redirect: verify state, resolve the user, issue a token."""
    if not sso.sso_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='sso is not configured')
    try:
        sso.verify_state_token(state)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid sso state') from exc
    try:
        identity = sso.exchange_code_for_identity(code)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail='identity provider exchange failed'
        ) from exc

    user = _resolve_sso_user(session, identity)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='account disabled')
    token = _issue_token(user)
    # The token travels in the URL fragment so it is never sent to a server in
    # the browser's request line or access logs.
    return RedirectResponse(
        sso.frontend_login_url(f'access_token={token.access_token}'),
        status_code=status.HTTP_302_FOUND,
    )


def _resolve_sso_user(session: Session, identity: dict[str, str | bool]) -> User:
    """Link an SSO identity to an existing account or provision a new one.

    An existing account is only ever linked — and a new account only ever
    provisioned — when the provider asserts the email address is verified
    (``email_verified`` is true). Without that assertion, an attacker who
    controls an unverified address at a provider could link to (and
    therefore authenticate as) any matching account, including
    administrators: the classic OIDC unverified-email account takeover.
    Identities already linked by subject are trusted, since that binding was
    established under the verified-email rule.

    Provisioned accounts always receive the unprivileged default role inside
    the configured default institution — SSO can never mint an administrator.
    """
    provider = settings.sso_provider
    email = identity['email'].lower()
    email_verified = bool(identity.get('email_verified'))
    user = session.exec(
        select(User).where(User.external_subject == identity['sub'], User.external_provider == provider)
    ).first()
    if user is not None:
        return user

    user = session.exec(select(User).where(User.email == email)).first()
    if user is not None:
        if not email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='email not verified by provider',
            )
        # Existing account (any role) opts into SSO by signing in once —
        # but only with a provider-verified email address.
        user.external_subject = identity['sub']
        user.external_provider = provider
        session.add(user)
        session.commit()
        return user

    if not email_verified:
        # Same rule for provisioning: an unverified address must not be able
        # to create accounts that shadow someone else's email.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='email not verified by provider',
        )

    institution = session.exec(
        select(Institution).where(Institution.slug == settings.sso_default_institution_slug)
    ).first()
    if institution is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='sso default institution missing')

    base_username = email.split('@')[0][:48]
    username = base_username
    suffix = 1
    while session.exec(select(User).where(User.username == username)).first() is not None:
        suffix += 1
        username = f'{base_username}{suffix}'
    if settings.sso_default_role not in ALL_ROLES:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='invalid sso default role')

    user = User(
        username=username,
        email=email,
        password_hash='',
        full_name=identity.get('name') or email,
        role=settings.sso_default_role,
        institution_id=institution.id,
        external_subject=identity['sub'],
        external_provider=provider,
    )
    session.add(user)
    session.add(
        AuditEvent(
            institution_id=institution.id,
            user_email=email,
            event_type='sso_provisioned',
            message=f'Account provisioned via {provider} single sign-on',
        )
    )
    session.commit()
    session.refresh(user)
    return user


legacy_router = APIRouter(tags=['auth'])


@legacy_router.get('/sso/config')
def legacy_sso_config() -> dict[str, Any]:
    """Backwards-compatible alias for the SSO discovery endpoint."""
    return _sso_config_payload()
