"""Pydantic schemas for user and admin requests and responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from backend.models.api_key import KeyListOut
from backend.security import BCRYPT_MAX_BYTES


def _new_password_rules(v: str) -> str:
    """Every password that gets stored: at least 8 characters (Field) and at most bcrypt's 72 bytes."""
    if len(v.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"password must be at most {BCRYPT_MAX_BYTES} bytes")
    return v


class RegisterRequest(BaseModel):
    """Body of POST /api/admin/register (new admin) and POST /api/admin/users (new user)."""

    user_name: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        return _new_password_rules(v)


class PasswordChange(BaseModel):
    """Body of PATCH /api/me/password."""

    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        return _new_password_rules(v)


class PasswordReset(BaseModel):
    """Body of PATCH /api/admin/users/{user_id}/password."""

    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        return _new_password_rules(v)


class UserOut(BaseModel):
    """A user as returned by the API (never includes the password hash)."""

    id: int
    user_name: str
    type: str
    created_by: int | None  # the admin who created this account; null for admins
    created_at: datetime


class UserListOut(UserOut):
    """A user in the admin's lists: deleted users are included and tagged with is_deleted."""

    is_deleted: bool
    deleted_by: int | None
    deleted_at: datetime | None
    key_count: int  # live (not deleted) API keys


class UserDetailOut(UserListOut):
    """GET /api/admin/users/{user_id}: the user and all their API keys (deleted ones tagged)."""

    keys: list[KeyListOut]


class LoginRequest(BaseModel):
    """Body of POST /api/admin/login and /api/user/login."""

    user_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class UserDeletedOut(BaseModel):
    """Result of DELETE /api/admin/users/{user_id}."""

    user: UserOut
    deleted_by: int
    deleted_at: datetime
    api_keys_revoked: int


class TokenOut(BaseModel):
    """Login result: send `access_token` as `Authorization: Bearer <token>` on later requests."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut
