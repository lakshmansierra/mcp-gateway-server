"""Pydantic schemas for user and admin requests and responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from backend.security import BCRYPT_MAX_BYTES


class RegisterRequest(BaseModel):
    """Body of POST /api/admin/register and /api/user/register."""

    user_name: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"password must be at most {BCRYPT_MAX_BYTES} bytes")
        return v


class UserOut(BaseModel):
    """A user as returned by the API (never includes the password hash)."""

    id: int
    user_name: str
    type: str
    created_at: datetime


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
