"""Who is calling: FastAPI dependencies that check the caller.

Protect a route with `admin: UserOut = Depends(current_admin)` (logged-in admin), or with
`dependencies=[Depends(require_admin_register_key)]` (the ADMIN_REGISTER_KEY from .env).
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from hdbcli import dbapi

from backend.config import get_settings
from backend.db import get_db, users
from backend.models import UserOut
from backend.security import decode_access_token

# Two separate schemes so /docs shows two boxes under "Authorize": one for the login token, one for the register key.
_login_token = HTTPBearer(auto_error=False, scheme_name="LoginToken", description="access_token from a login route")
_register_key = HTTPBearer(auto_error=False, scheme_name="AdminRegisterKey", description="ADMIN_REGISTER_KEY from .env")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


@dataclass(frozen=True)
class Session:
    """The login token this request came with: who it belongs to, its id, and when it expires."""

    user: UserOut
    jti: str
    expires_at: datetime  # UTC


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_login_token),
    conn: dbapi.Connection = Depends(get_db),
) -> Session:
    """Check the login token. It is refused if it is forged or expired, if the user was deleted, if this token
    was logged out (its jti is in the revoked-token table), or if the user's password changed since it was
    issued (token_version moved on, which ends every device)."""
    if credentials is None:
        raise _unauthorized("Not logged in")
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = int(claims["sub"])
        token_version = int(claims["ver"])
        jti = str(claims["jti"])
        expires_at = datetime.fromtimestamp(int(claims["exp"]), UTC).replace(tzinfo=None)
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise _unauthorized("Invalid or expired token; log in again") from exc

    cur = conn.cursor()
    try:
        found = users.get_active_for_auth(cur, user_id, jti)
    finally:
        cur.close()
    if found is None:
        raise _unauthorized("User no longer exists")
    row, current_version, revoked = found
    if revoked:
        raise _unauthorized("Logged out on this device; log in again")
    if token_version != current_version:
        raise _unauthorized("Session ended (password changed or logged out on all devices); log in again")
    return Session(user=UserOut(**row._asdict()), jti=jti, expires_at=expires_at)


def current_user(session: Session = Depends(current_session)) -> UserOut:
    """The logged-in admin or user."""
    return session.user


def require_admin_register_key(credentials: HTTPAuthorizationCredentials | None = Depends(_register_key)) -> None:
    """Only callers holding ADMIN_REGISTER_KEY (sent as `Authorization: Bearer <key>`) may create admins."""
    expected = get_settings().admin_register_key
    if expected is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin registration is disabled: ADMIN_REGISTER_KEY is not set")
    if credentials is None or not hmac.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise _unauthorized("Invalid or missing admin register key")


def current_admin(user: UserOut = Depends(current_user)) -> UserOut:
    if user.type != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user
