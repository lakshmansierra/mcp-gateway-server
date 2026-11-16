"""User accounts.

POST /api/user/register  creates an account with type 'user' (sign-up from the UI)
POST /api/user/login     checks the password and returns a login token (users only; admins use /api/admin/login)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from hdbcli import dbapi

from backend.db import get_db
from backend.models import LoginRequest, RegisterRequest, TokenOut, UserOut
from backend.services import accounts

router = APIRouter(prefix="/api/user", tags=["user"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(body: RegisterRequest, conn: dbapi.Connection = Depends(get_db)) -> UserOut:
    return accounts.register(conn, body, "user")


@router.post("/login", response_model=TokenOut)
def login_user(body: LoginRequest, conn: dbapi.Connection = Depends(get_db)) -> TokenOut:
    return accounts.login(conn, body, "user")
