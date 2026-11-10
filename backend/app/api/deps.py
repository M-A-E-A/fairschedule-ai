"""FastAPI dependencies: authentication, role checks, and tenant checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.db import get_session
from app.core.security import JWTError, decode_access_token
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)

U = TypeVar('U')


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the bearer token to an active user, or raise 401/403."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='missing token')
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get('sub', 0))
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid token') from exc
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='user not found')
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='account disabled')
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    """Dependency factory enforcing that the caller holds one of ``roles``.

    Role checks always read the user row from the database (not the token), so
    a revoked or demoted account loses access immediately.
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'role {user.role!r} is not permitted to perform this action',
            )
        return user

    return dependency


def ensure_tenant(user: User, institution_id: int | None) -> None:
    """Reject any request targeting another tenant's institution id."""
    if institution_id is None or user.institution_id != institution_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='tenant mismatch')


def ensure_active_user(user: User) -> User:
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='account disabled')
    return user


__all__ = ['ensure_active_user', 'ensure_tenant', 'get_current_user', 'require_roles']
