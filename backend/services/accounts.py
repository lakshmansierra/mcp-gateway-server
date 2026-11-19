"""Register and log in accounts. Admins and users share this logic; only the account type differs."""

from __future__ import annotations

from typing import Literal

from fastapi import HTTPException, status
from hdbcli import dbapi

from backend.db import users
from backend.models import LoginRequest, RegisterRequest, TokenOut, UserOut
from backend.security import create_access_token, hash_password, verify_password

AccountType = Literal["admin", "user"]

# One message for every failed login, so it doesn't reveal whether the user name exists.
LOGIN_FAILED = "Invalid user name or password"


def register(
    conn: dbapi.Connection, body: RegisterRequest, account_type: AccountType, created_by: int | None = None
) -> UserOut:
    """Create an account. `created_by` is the admin creating a user; None for admins (made with ADMIN_REGISTER_KEY)."""
    cur = conn.cursor()
    try:
        # user_name is UNIQUE in the table, deleted users included, so a deleted user's name stays taken.
        # The lookup ignores case so "Lax" and "lax" can't both exist. Names are shared by admins and users.
        deleted = users.find_by_name(cur, body.user_name)
        if deleted is not None:
            detail = "belongs to a deleted user" if deleted else "already exists"
            raise HTTPException(status.HTTP_409_CONFLICT, f"User name '{body.user_name}' {detail}")

        row = users.insert(cur, body.user_name, hash_password(body.password), account_type, created_by)
        conn.commit()
    except HTTPException:
        raise
    except dbapi.IntegrityError as exc:
        # Two requests registered the same name at the same moment: the UNIQUE constraint stopped the second.
        conn.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"User name '{body.user_name}' already exists") from exc
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return UserOut(**row._asdict())


def login(conn: dbapi.Connection, body: LoginRequest, account_type: AccountType) -> TokenOut:
    """Admins log in only on the admin route and users only on the user route."""
    cur = conn.cursor()
    try:
        row = users.get_for_login(cur, body.user_name)
    except dbapi.Error as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    # verify_password runs even when the user doesn't exist, so both cases take the same time.
    password_ok = verify_password(body.password, row.password_hash if row else None)
    if row is None or not password_ok or row.is_deleted or row.type != account_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)

    token, expires_in = create_access_token(row.id, row.user_name, row.type, row.token_version)
    user = UserOut(id=row.id, user_name=row.user_name, type=row.type, created_by=row.created_by, created_at=row.created_at)
    return TokenOut(access_token=token, expires_in=expires_in, user=user)
