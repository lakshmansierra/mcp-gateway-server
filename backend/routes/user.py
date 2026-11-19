"""User accounts.

POST /api/user/login  checks the password and returns a login token (users only; admins use /api/admin/login)

Users can't sign up themselves: an admin creates them with POST /api/admin/users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from hdbcli import dbapi

from backend.db import get_db
from backend.models import LoginRequest, TokenOut
from backend.services import accounts

router = APIRouter(prefix="/api/user", tags=["user"])


@router.post("/login", response_model=TokenOut)
def login_user(body: LoginRequest, conn: dbapi.Connection = Depends(get_db)) -> TokenOut:
    return accounts.login(conn, body, "user")
