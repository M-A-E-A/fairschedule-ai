"""Password hashing and JWT issue/verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


# A valid bcrypt hash of a random string, fixed forever. Login verification
# runs `verify_password` against this when no stored hash is available (user
# not found, or an SSO account with no password), so an unknown username
# pays the same bcrypt cost as a known one: response timing cannot reveal
# which accounts exist.
DUMMY_PASSWORD_HASH = '$2b$12$1rK0TCII1lu7Jd5bHsIHAe5Ped.wlqN7fr6R1mSPyf9ZKQ10O7o3e'



def create_access_token(user_id: int, role: str, institution_id: int) -> str:
    """Issue a short-lived bearer token.

    ``sub`` is the immutable user id (not the email or username, which can
    change), so revocation-sensitive lookups always resolve to one row.
    """
    now = datetime.now(UTC)
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


__all__ = [
    'DUMMY_PASSWORD_HASH',
    'JWTError',
    'create_access_token',
    'decode_access_token',
    'hash_password',
    'verify_password',
]
