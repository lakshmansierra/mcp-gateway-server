"""SQL for the user table (USER_TABLE in .env)."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from hdbcli import dbapi

from backend.config import get_settings
from backend.db import api_keys, revoked_tokens


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


def table() -> str:
    return _table()


def managed_ids_sql() -> str:
    """Subquery: the ids of the accounts an admin manages, i.e. the admin and the users they created (the same rule
    as services/ownership.py). Takes two parameters, both the admin's id: `"user_id" IN ({managed_ids_sql()})`."""
    return f'SELECT "id" FROM {_table()} WHERE "id" = ? OR ("type" = \'user\' AND "created_by" = ?)'


class UserListRow(NamedTuple):
    id: int
    user_name: str
    type: str
    created_by: int | None
    created_at: datetime
    is_deleted: int
    deleted_by: int | None
    deleted_at: datetime | None
    key_count: int  # live (not deleted) API keys


def _list_sql(where: str) -> str:
    return (
        f'SELECT u."id", u."user_name", u."type", u."created_by", u."created_at", u."is_deleted", u."deleted_by", '
        f'u."deleted_at", (SELECT COUNT(*) FROM {api_keys.table()} k WHERE k."user_id" = u."id" AND k."is_deleted" = 0) '
        f"FROM {_table()} u WHERE {where}"
    )


def list_created_by(cur: dbapi.Cursor, admin_id: int) -> list[UserListRow]:
    """The users this admin created, deleted ones included, newest first."""
    cur.execute(_list_sql('u."type" = \'user\' AND u."created_by" = ?') + ' ORDER BY u."id" DESC', (admin_id,))
    return [UserListRow(*row) for row in cur.fetchall()]


def get_managed(cur: dbapi.Cursor, user_id: int, admin_id: int) -> UserListRow | None:
    """This account if the admin manages it (it is the admin, or a user they created), deleted or not; else None."""
    cur.execute(
        _list_sql('u."id" = ? AND (u."id" = ? OR (u."type" = \'user\' AND u."created_by" = ?))'),
        (user_id, admin_id, admin_id),
    )
    row = cur.fetchone()
    return None if row is None else UserListRow(*row)


class LoginRow(NamedTuple):
    id: int
    user_name: str
    type: str
    created_by: int | None
    created_at: datetime
    password_hash: str
    is_deleted: bool
    token_version: int


def get_for_login(cur: dbapi.Cursor, user_name: str) -> LoginRow | None:
    """The user with this name (any case), including the password hash, or None."""
    cur.execute(
        f'SELECT {_USER_COLUMNS}, "password_hash", "is_deleted", "token_version" '
        f'FROM {_table()} WHERE LOWER("user_name") = LOWER(?)',
        (user_name,),
    )
    row = cur.fetchone()
    return None if row is None else LoginRow(*row[:6], bool(row[6]), row[7])


def get_active_for_auth(cur: dbapi.Cursor, user_id: int, jti: str) -> tuple[UserRow, int, bool] | None:
    """For checking a login token, in one query: the live user, their current token_version (the token must
    carry the same number), and whether this token (jti) was logged out. None if the user is missing or deleted."""
    cur.execute(
        f'SELECT {_USER_COLUMNS}, "token_version", '
        f'(SELECT COUNT(*) FROM {revoked_tokens.table()} WHERE "jti" = ?) '
        f'FROM {_table()} WHERE "id" = ? AND "is_deleted" = 0',
        (jti, user_id),
    )
    row = cur.fetchone()
    return None if row is None else (UserRow(*row[:5]), row[5], row[6] > 0)


def bump_token_version(cur: dbapi.Cursor, user_id: int) -> None:
    """Log the user out everywhere: every token issued so far stops working. The caller commits."""
    cur.execute(f'UPDATE {_table()} SET "token_version" = "token_version" + 1 WHERE "id" = ?', (user_id,))


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
    """Replace a live user's password hash and log them out everywhere (token_version + 1).
    False if missing or deleted. The caller commits."""
    cur.execute(
        f'UPDATE {_table()} SET "password_hash" = ?, "token_version" = "token_version" + 1 '
        f'WHERE "id" = ? AND "is_deleted" = 0',
        (password_hash, user_id),
    )
    return cur.rowcount > 0


def deleted_by(cur: dbapi.Cursor, user_id: int) -> int | None:
    """Who deleted this user (None if not deleted or no such user)."""
    cur.execute(f'SELECT "deleted_by" FROM {_table()} WHERE "id" = ?', (user_id,))
    row = cur.fetchone()
    return None if row is None else row[0]


def soft_delete(cur: dbapi.Cursor, user_id: int, deleted_by: int) -> datetime | None:
    """Mark the user deleted (the row is kept) and end their sessions (token_version + 1), so tokens
    from before the delete don't come back to life if the user is restored.
    Returns the deletion time, or None if already deleted."""
    table = _table()
    cur.execute(
        f'UPDATE {table} SET "is_deleted" = 1, "deleted_by" = ?, "deleted_at" = CURRENT_TIMESTAMP, '
        f'"token_version" = "token_version" + 1 '
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
