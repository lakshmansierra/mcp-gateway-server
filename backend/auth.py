"""Who is calling: FastAPI dependencies that check the caller.

Protect a route with `admin: UserOut = Depends(current_admin)` (logged-in admin), or with
`dependencies=[Depends(require_admin_register_key)]` (the ADMIN_REGISTER_KEY from .env).
"""

from __future__ import annotations

import hmac

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


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_login_token),
    conn: dbapi.Connection = Depends(get_db),
) -> UserOut:
    """The logged-in user. The token is checked, then the user is re-read so a deleted user is locked out at once."""
    if credentials is None:
        raise _unauthorized("Not logged in")
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise _unauthorized("Invalid or expired token; log in again") from exc

    cur = conn.cursor()
    try:
        row = users.get_active(cur, user_id)
    finally:
        cur.close()
    if row is None:
        raise _unauthorized("User no longer exists")
    return UserOut(**row._asdict())


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
