"""Admin accounts.

POST /api/admin/register  creates an account with type 'admin'. Called from Postman (the UI has no admin
                          sign-up) with `Authorization: Bearer <ADMIN_REGISTER_KEY from .env>`.
POST /api/admin/login     checks the password and returns a login token (admins only)
DELETE /api/admin/users/{user_id}
                          soft-deletes a user and revokes their API keys (logged-in admin only)
POST /api/admin/users/{user_id}/restore
                          undoes a user's soft delete (logged-in admin only)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from hdbcli import dbapi

from backend.auth import current_admin, require_admin_register_key
from backend.db import get_db
from backend.models import LoginRequest, RegisterRequest, TokenOut, UserDeletedOut, UserOut
from backend.services import accounts
from backend.services import users as user_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_register_key)],
)
def register_admin(body: RegisterRequest, conn: dbapi.Connection = Depends(get_db)) -> UserOut:
    return accounts.register(conn, body, "admin")


@router.post("/login", response_model=TokenOut)
def login_admin(body: LoginRequest, conn: dbapi.Connection = Depends(get_db)) -> TokenOut:
    return accounts.login(conn, body, "admin")


@router.delete("/users/{user_id}", response_model=UserDeletedOut)
def delete_user(
    user_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> UserDeletedOut:
    return user_service.delete_user(conn, user_id, admin)


@router.post("/users/{user_id}/restore", response_model=UserOut)
def restore_user(
    user_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> UserOut:
    return user_service.restore_user(conn, user_id)
