"""SQL for the revoked-token table (REVOKED_TOKEN_TABLE in .env).

Holds the ids (jti) of login tokens that were logged out before they expired. Tokens themselves are never
stored. A row is only needed until the token would have expired anyway, then it can be purged.
"""

from __future__ import annotations

from datetime import datetime

from hdbcli import dbapi

from backend.config import get_settings


def table() -> str:
    s = get_settings()
    return s.table(s.revoked_token_table)


def revoke(cur: dbapi.Cursor, jti: str, user_id: int, expires_at: datetime) -> None:
    """Mark one token as logged out. Logging out the same token twice is harmless. The caller commits."""
    cur.execute(f'SELECT COUNT(*) FROM {table()} WHERE "jti" = ?', (jti,))
    if cur.fetchone()[0]:
        return
    cur.execute(
        f'INSERT INTO {table()} ("jti", "user_id", "expires_at") VALUES (?, ?, ?)',
        (jti, user_id, expires_at),
    )


def purge_expired(cur: dbapi.Cursor) -> int:
    """Delete rows for tokens that have expired anyway. Returns how many. The caller commits."""
    cur.execute(f'DELETE FROM {table()} WHERE "expires_at" < CURRENT_UTCTIMESTAMP')
    return cur.rowcount
