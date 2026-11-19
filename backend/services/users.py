"""Managing users (admin actions)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from hdbcli import dbapi

from backend.db import api_keys, revoked_tokens, users
from backend.models import PasswordChange, PasswordReset, UserDeletedOut, UserOut
from backend.security import hash_password, verify_password


def _save_password(conn: dbapi.Connection, cur: dbapi.Cursor, user_id: int, new_password: str) -> None:
    if not users.set_password_hash(cur, user_id, hash_password(new_password)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
    conn.commit()


def logout_this_device(conn: dbapi.Connection, user_id: int, jti: str, expires_at: datetime) -> None:
    """End only the session this token belongs to: its id goes into the revoked-token table.
    Rows for tokens that have expired anyway are cleaned up at the same time."""
    cur = conn.cursor()
    try:
        revoked_tokens.revoke(cur, jti, user_id, expires_at)
        revoked_tokens.purge_expired(cur)
        conn.commit()
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()


def logout_everywhere(conn: dbapi.Connection, me: UserOut) -> None:
    """End every session of this account on every device (token_version + 1)."""
    cur = conn.cursor()
    try:
        users.bump_token_version(cur, me.id)
        conn.commit()
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()


def change_own_password(conn: dbapi.Connection, me: UserOut, body: PasswordChange) -> None:
    """Any logged-in admin or user changes their own password; the old one must be given."""
    cur = conn.cursor()
    try:
        current_hash = users.get_password_hash(cur, me.id)
        if current_hash is None or not verify_password(body.old_password, current_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Old password is wrong")
        if verify_password(body.new_password, current_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must differ from the old one")
        _save_password(conn, cur, me.id, body.new_password)
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()


def reset_password(conn: dbapi.Connection, user_id: int, body: PasswordReset, admin: UserOut) -> UserOut:
    """An admin sets a new password (no old one needed) for themselves or for a user they created.

    Not for other admins, or for users another admin created. Deleted accounts can't be reset.
    """
    cur = conn.cursor()
    try:
        found = users.get_by_id(cur, user_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
        target, is_deleted = found
        if not (target.id == admin.id or (target.type == "user" and target.created_by == admin.id)):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "You can only reset your own password or those of users you created"
            )
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"User '{target.user_name}' is deleted")
        _save_password(conn, cur, user_id, body.new_password)
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return UserOut(**target._asdict())


def delete_user(conn: dbapi.Connection, user_id: int, admin: UserOut) -> UserDeletedOut:
    """Soft-delete a user and revoke their API keys in one transaction.

    The row stays (is_deleted = 1, deleted_by = the admin, deleted_at = now), so the name stays taken and the
    history is kept. Their login stops working at once, and so do their gateway keys.
    An admin may delete only the users they created (created_by); no admin can be deleted, not even yourself.
    """
    cur = conn.cursor()
    try:
        found = users.get_by_id(cur, user_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
        user, is_deleted = found
        if user.type != "user":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins can't be deleted")
        if user.created_by != admin.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete users you created")
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"User '{user.user_name}' is already deleted")

        deleted_at = users.soft_delete(cur, user_id, admin.id)
        if deleted_at is None:  # deleted by another request in the meantime
            raise HTTPException(status.HTTP_409_CONFLICT, f"User '{user.user_name}' is already deleted")
        revoked = api_keys.soft_delete_for_user(cur, user_id, admin.id)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return UserDeletedOut(user=UserOut(**user._asdict()), deleted_by=admin.id, deleted_at=deleted_at, api_keys_revoked=revoked)


def restore_user(conn: dbapi.Connection, user_id: int, admin: UserOut) -> UserOut:
    """Undo a user's soft delete, so they can log in again. An admin may restore only users they deleted.

    Their API keys stay revoked: the table can't tell keys revoked with the user from keys deleted earlier
    on purpose, so the user creates new keys after being restored.
    """
    cur = conn.cursor()
    try:
        found = users.get_by_id(cur, user_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
        user, is_deleted = found
        if user.type != "user":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only user accounts can be restored, not admins")
        if not is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"User '{user.user_name}' is not deleted")
        if users.deleted_by(cur, user_id) != admin.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only restore users you deleted")
        if not users.restore(cur, user_id):
            raise HTTPException(status.HTTP_409_CONFLICT, f"User '{user.user_name}' is not deleted")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return UserOut(**user._asdict())
