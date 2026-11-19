"""Admin accounts.

POST /api/admin/register  creates an account with type 'admin'. Called from Postman (the UI has no admin
                          sign-up) with `Authorization: Bearer <ADMIN_REGISTER_KEY from .env>`.
POST /api/admin/login     checks the password and returns a login token (admins only)
POST /api/admin/users     creates a user account (logged-in admin only; users can't sign up themselves).
                          The user is saved with created_by = this admin.
DELETE /api/admin/users/{user_id}
                          soft-deletes a user you created and revokes their API keys (admins can't be deleted)
POST /api/admin/users/{user_id}/restore
                          undoes the soft delete of a user you deleted
PATCH /api/admin/users/{user_id}/password
                          sets a new password for yourself or a user you created (no old password needed)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from hdbcli import dbapi

from backend.auth import current_admin, require_admin_register_key
from backend.db import get_db
from backend.models import LoginRequest, PasswordReset, RegisterRequest, TokenOut, UserDeletedOut, UserOut
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


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: RegisterRequest,
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> UserOut:
    return accounts.register(conn, body, "user", created_by=admin.id)


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
    return user_service.restore_user(conn, user_id, admin)


@router.patch("/users/{user_id}/password", response_model=UserOut)
def reset_password(
    body: PasswordReset,
    user_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> UserOut:
    return user_service.reset_password(conn, user_id, body, admin)
