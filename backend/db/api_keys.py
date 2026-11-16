"""SQL for the client-to-gateway API key table (MCP_CLIENT_TO_GATEWAY_API_KEY_TABLE in .env)."""

from __future__ import annotations

from hdbcli import dbapi

from backend.config import get_settings


def _table() -> str:
    s = get_settings()
    return s.table(s.api_key_table)


def soft_delete_for_user(cur: dbapi.Cursor, user_id: int, deleted_by: int) -> int:
    """Revoke all of a user's live keys. Returns how many were revoked. The caller commits."""
    cur.execute(
        f'UPDATE {_table()} SET "is_deleted" = 1, "deleted_by" = ?, "deleted_at" = CURRENT_TIMESTAMP '
        f'WHERE "user_id" = ? AND "is_deleted" = 0',
        (deleted_by, user_id),
    )
    return cur.rowcount
