"""Application settings.

All configuration comes from environment variables (see .env.example).
Secrets are never hardcoded: JWT_SECRET must be provided in production and
an ephemeral random secret is generated for development/test runs instead.
"""

from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = 'development'
    database_url: str = 'sqlite:///./demo.db'
    jwt_secret: str = ''
    jwt_expire_minutes: int = 480
    backend_cors_origins: str = 'http://localhost:5173'
    frontend_url: str = 'http://localhost:5173'
    # Browser-facing base URL of this API (used to build the SSO redirect URI).
    public_base_url: str = 'http://localhost:8000'
    ai_provider: str = 'none'
    ai_api_key: str = ''

    # Google OAuth / university OIDC single sign-on.
    sso_provider: str = 'google'  # 'google' | 'oidc' | 'none'
    google_client_id: str = ''
    google_client_secret: str = ''
    oidc_authorize_url: str = 'https://accounts.google.com/o/oauth2/v2/auth'
    oidc_token_url: str = 'https://oauth2.googleapis.com/token'
    oidc_userinfo_url: str = 'https://openidconnect.googleapis.com/v1/userinfo'
    oidc_scopes: str = 'openid email profile'
    sso_redirect_path: str = '/auth/sso/callback'
    # Users who arrive via SSO without an existing account are provisioned
    # into this institution with this role (never a privileged role).
    sso_default_institution_slug: str = 'northbridge'
    sso_default_role: str = 'student'

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    @model_validator(mode='after')
    def ensure_jwt_secret(self) -> 'Settings':
        if not self.jwt_secret:
            if self.app_env == 'production':
                raise ValueError('JWT_SECRET must be set when APP_ENV=production')
            # Ephemeral, per-process secret for development/test: never a
            # hardcoded value that ships in the repository.
            self.jwt_secret = secrets.token_urlsafe(32)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
