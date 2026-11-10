"""Request/response schemas for authentication endpoints."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    """Sign in with an app-managed username (primary) or an email address."""

    username: str | None = None
    email: EmailStr | None = None
    password: str

    @model_validator(mode='after')
    def require_identifier(self) -> LoginRequest:
        if not self.username and not self.email:
            raise ValueError('either username or email is required')
        return self


class AuthToken(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    role: str
    institution_id: int
    username: str
    full_name: str


class MeResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: str
    role: str
    institution_id: int
    institution_name: str = ''
    student_group_id: int | None = None
    lecturer_id: int | None = None


class SsoConfigResponse(BaseModel):
    enabled: bool
    provider: str
    login_url: str = ''
    client_id: str = ''
    redirect_uri: str = ''


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r'^[A-Za-z0-9._-]+$')
    email: EmailStr
    full_name: str = Field(default='', max_length=120)
    role: str
    password: str = Field(min_length=8, max_length=128)
    student_group_id: int | None = None
    lecturer_id: int | None = None
    is_active: bool = True


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    student_group_id: int | None = None
    lecturer_id: int | None = None
    is_active: bool | None = None
    clear_links: bool = False
