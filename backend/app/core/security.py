"""Password hashing and JWT issue/verification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

ALGORITHM = 'HS256'


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(user_id: int, role: str, institution_id: int) -> str:
    """Issue a short-lived bearer token.

    ``sub`` is the immutable user id (not the email or username, which can
    change), so revocation-sensitive lookups always resolve to one row.
    """
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user_id),
        'role': role,
        'institution_id': institution_id,
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode a bearer token, raising JWTError on any invalid input."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


__all__ = ['JWTError', 'create_access_token', 'decode_access_token', 'hash_password', 'verify_password']
