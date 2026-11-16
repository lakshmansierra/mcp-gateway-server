"""Managing users (admin actions)."""

from __future__ import annotations

from fastapi import HTTPException, status
from hdbcli import dbapi

from backend.db import api_keys, users
from backend.models import UserDeletedOut, UserOut


def delete_user(conn: dbapi.Connection, user_id: int, admin: UserOut) -> UserDeletedOut:
    """Soft-delete a user and revoke their API keys in one transaction.

    The row stays (is_deleted = 1, deleted_by = the admin, deleted_at = now), so the name stays taken and the
    history is kept. Their login stops working at once, and so do their gateway keys.
    Only accounts of type 'user' can be deleted here; admins are not.
    """
    cur = conn.cursor()
    try:
        found = users.get_by_id(cur, user_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
        user, is_deleted = found
        if user.type != "user":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only user accounts can be deleted, not admins")
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


def restore_user(conn: dbapi.Connection, user_id: int) -> UserOut:
    """Undo a user's soft delete, so they can log in again.

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
        if not is_deleted or not users.restore(cur, user_id):
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
