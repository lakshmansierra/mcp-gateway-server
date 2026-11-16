"""SQL for the user table (USER_TABLE in .env)."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from hdbcli import dbapi

from backend.config import get_settings


class UserRow(NamedTuple):
    id: int
    user_name: str
    type: str
    created_by: int | None  # the admin who created this account; NULL for admins
    created_at: datetime


_USER_COLUMNS = '"id", "user_name", "type", "created_by", "created_at"'


def _table() -> str:
    s = get_settings()
    return s.table(s.user_table)


class LoginRow(NamedTuple):
    id: int
    user_name: str
    type: str
    created_by: int | None
    created_at: datetime
    password_hash: str
    is_deleted: bool


def get_for_login(cur: dbapi.Cursor, user_name: str) -> LoginRow | None:
    """The user with this name (any case), including the password hash, or None."""
    cur.execute(
        f'SELECT {_USER_COLUMNS}, "password_hash", "is_deleted" '
        f'FROM {_table()} WHERE LOWER("user_name") = LOWER(?)',
        (user_name,),
    )
    row = cur.fetchone()
    return None if row is None else LoginRow(*row[:6], bool(row[6]))


def get_active(cur: dbapi.Cursor, user_id: int) -> UserRow | None:
    """The user with this id, unless deleted."""
    cur.execute(
        f'SELECT {_USER_COLUMNS} FROM {_table()} WHERE "id" = ? AND "is_deleted" = 0',
        (user_id,),
    )
    row = cur.fetchone()
    return None if row is None else UserRow(*row)


def get_by_id(cur: dbapi.Cursor, user_id: int) -> tuple[UserRow, bool] | None:
    """The user with this id and whether they are deleted, or None if no such id."""
    cur.execute(
        f'SELECT {_USER_COLUMNS}, "is_deleted" FROM {_table()} WHERE "id" = ?',
        (user_id,),
    )
    row = cur.fetchone()
    return None if row is None else (UserRow(*row[:5]), bool(row[5]))


def get_password_hash(cur: dbapi.Cursor, user_id: int) -> str | None:
    """The stored bcrypt hash of a live user, or None if missing or deleted."""
    cur.execute(f'SELECT "password_hash" FROM {_table()} WHERE "id" = ? AND "is_deleted" = 0', (user_id,))
    row = cur.fetchone()
    return None if row is None else row[0]


def set_password_hash(cur: dbapi.Cursor, user_id: int, password_hash: str) -> bool:
    """Replace a live user's password hash. False if missing or deleted. The caller commits."""
    cur.execute(
        f'UPDATE {_table()} SET "password_hash" = ? WHERE "id" = ? AND "is_deleted" = 0',
        (password_hash, user_id),
    )
    return cur.rowcount > 0


def deleted_by(cur: dbapi.Cursor, user_id: int) -> int | None:
    """Who deleted this user (None if not deleted or no such user)."""
    cur.execute(f'SELECT "deleted_by" FROM {_table()} WHERE "id" = ?', (user_id,))
    row = cur.fetchone()
    return None if row is None else row[0]


def soft_delete(cur: dbapi.Cursor, user_id: int, deleted_by: int) -> datetime | None:
    """Mark the user deleted (the row is kept). Returns the deletion time, or None if already deleted."""
    table = _table()
    cur.execute(
        f'UPDATE {table} SET "is_deleted" = 1, "deleted_by" = ?, "deleted_at" = CURRENT_TIMESTAMP '
        f'WHERE "id" = ? AND "is_deleted" = 0',
        (deleted_by, user_id),
    )
    if cur.rowcount == 0:
        return None
    cur.execute(f'SELECT "deleted_at" FROM {table} WHERE "id" = ?', (user_id,))
    return cur.fetchone()[0]


def restore(cur: dbapi.Cursor, user_id: int) -> bool:
    """Undo a soft delete. False if the user isn't deleted. The caller commits."""
    cur.execute(
        f'UPDATE {_table()} SET "is_deleted" = 0, "deleted_by" = NULL, "deleted_at" = NULL '
        f'WHERE "id" = ? AND "is_deleted" = 1',
        (user_id,),
    )
    return cur.rowcount > 0


def find_by_name(cur: dbapi.Cursor, user_name: str) -> bool | None:
    """None if no user has this name (any case); otherwise whether that user is deleted."""
    cur.execute(f'SELECT "is_deleted" FROM {_table()} WHERE LOWER("user_name") = LOWER(?)', (user_name,))
    row = cur.fetchone()
    return None if row is None else bool(row[0])


def insert(
    cur: dbapi.Cursor, user_name: str, password_hash: str, user_type: str, created_by: int | None = None
) -> UserRow:
    """Insert a user and return the saved row. The caller commits."""
    table = _table()
    cur.execute(
        f'INSERT INTO {table} ("user_name", "password_hash", "type", "created_by", "is_deleted") VALUES (?, ?, ?, ?, 0)',
        (user_name, password_hash, user_type, created_by),
    )
    cur.execute("SELECT CURRENT_IDENTITY_VALUE() FROM DUMMY")
    new_id = cur.fetchone()[0]
    cur.execute(f'SELECT {_USER_COLUMNS} FROM {table} WHERE "id" = ?', (new_id,))
    return UserRow(*cur.fetchone())
