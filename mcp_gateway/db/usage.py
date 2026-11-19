"""Write tool usage to HANA: each server's tools and their history, and every tool call.

  tools_mgs         one row per tool a server has ever listed (mcp_id = the server's row id). A tool that
                    disappears gets removed_at; one that comes back gets removed_at = NULL again. Never deleted.
  tool_changes_mgs  one row per change: 'added', 'removed' or 'changed' (description or input schema), with the
                    tool's description and schema before (old_value) and after (new_value), as JSON.
  tool_calls_mgs    one row per tools/call: which tool, which key and user, when, how long, ok / error / timeout.

Unlike the rest of mcp_gateway/db/ (read-only), the gateway writes these. Every function here runs inside the
caller's transaction; the caller commits or rolls back.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hdbcli import dbapi

from mcp_gateway.config.settings import DatabaseSettings

logger = logging.getLogger(__name__)

ERROR_MESSAGE_MAX = 5000  # tool_calls_mgs.error_message is NVARCHAR(5000)


@dataclass(frozen=True)
class ToolInfo:
    """A tool as a server lists it: what tools_mgs stores about it."""

    name: str
    description: str | None
    input_schema: str | None  # JSON, keys sorted, so the same schema always gives the same text

    def as_json(self) -> str:
        return json.dumps({"description": self.description, "input_schema": _loads(self.input_schema)})


@dataclass(frozen=True)
class ToolCall:
    """One tools/call, waiting to be written."""

    mcp_id: int
    tool_name: str
    key_id: int
    user_id: int
    called_at: datetime  # UTC, naive (like the tables' CURRENT_TIMESTAMP on HANA Cloud)
    duration_ms: int
    status: str  # ok / error / timeout
    error_message: str | None


@dataclass
class SyncResult:
    added: int = 0
    removed: int = 0
    changed: int = 0

    def __bool__(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def _loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)


def _text(value: Any) -> str | None:
    """NCLOB columns come back as LOB objects; read them into str."""
    if value is None or isinstance(value, str):
        return value
    return value.read()


def sync_tools(cur: dbapi.Cursor, db: DatabaseSettings, mcp_id: int, tools: list[ToolInfo]) -> SyncResult:
    """Make tools_mgs match what server `mcp_id` lists now, logging each difference in tool_changes_mgs.

    The server's rows are locked first (FOR UPDATE): when several gateway instances see the same change, the
    second waits for the first, then finds nothing left to do, so each change is logged once. A brand-new tool
    has no row to lock; there the unique (mcp_id, tool_name) key stops the second insert (IntegrityError), and
    the caller rolls back and retries on the next round.
    """
    tools_t, changes_t = db.table(db.tool_table), db.table(db.tool_change_table)
    cur.execute(
        f'SELECT "id", "tool_name", "description", "input_schema", "removed_at" FROM {tools_t} '
        f'WHERE "mcp_id" = ? FOR UPDATE',
        (mcp_id,),
    )
    stored = {
        name: (tool_id, ToolInfo(name, _text(description), _text(schema)), removed_at)
        for tool_id, name, description, schema, removed_at in cur.fetchall()
    }
    now_listed = {t.name: t for t in tools}
    result = SyncResult()

    def log_change(tool_id: int, change: str, old: ToolInfo | None, new: ToolInfo | None) -> None:
        cur.execute(
            f'INSERT INTO {changes_t} ("tool_id", "change_type", "old_value", "new_value") VALUES (?, ?, ?, ?)',
            (tool_id, change, old.as_json() if old else None, new.as_json() if new else None),
        )

    for name, tool in now_listed.items():
        row = stored.get(name)
        if row is None:
            cur.execute(
                f'INSERT INTO {tools_t} ("mcp_id", "tool_name", "description", "input_schema") VALUES (?, ?, ?, ?)',
                (mcp_id, name, tool.description, tool.input_schema),
            )
            cur.execute("SELECT CURRENT_IDENTITY_VALUE() FROM DUMMY")
            log_change(cur.fetchone()[0], "added", None, tool)
            result.added += 1
            continue
        tool_id, old, removed_at = row
        if removed_at is not None:  # it was gone and is back
            cur.execute(
                f'UPDATE {tools_t} SET "removed_at" = NULL, "description" = ?, "input_schema" = ? WHERE "id" = ?',
                (tool.description, tool.input_schema, tool_id),
            )
            log_change(tool_id, "added", None, tool)
            result.added += 1
        elif (old.description, _loads(old.input_schema)) != (tool.description, _loads(tool.input_schema)):
            cur.execute(
                f'UPDATE {tools_t} SET "description" = ?, "input_schema" = ? WHERE "id" = ?',
                (tool.description, tool.input_schema, tool_id),
            )
            log_change(tool_id, "changed", old, tool)
            result.changed += 1

    for name, (tool_id, old, removed_at) in stored.items():
        if name not in now_listed and removed_at is None:
            cur.execute(f'UPDATE {tools_t} SET "removed_at" = CURRENT_TIMESTAMP WHERE "id" = ?', (tool_id,))
            log_change(tool_id, "removed", old, None)
            result.removed += 1
    return result


def tool_ids(cur: dbapi.Cursor, db: DatabaseSettings, mcp_ids: set[int]) -> dict[tuple[int, str], int]:
    """(mcp_id, tool_name) -> tools_mgs.id for these servers, removed tools included (a call may arrive just
    after its tool disappeared)."""
    if not mcp_ids:
        return {}
    placeholders = ", ".join("?" for _ in mcp_ids)
    cur.execute(
        f'SELECT "mcp_id", "tool_name", "id" FROM {db.table(db.tool_table)} WHERE "mcp_id" IN ({placeholders})',
        tuple(mcp_ids),
    )
    return {(mcp_id, name): tool_id for mcp_id, name, tool_id in cur.fetchall()}


def insert_calls(cur: dbapi.Cursor, db: DatabaseSettings, rows: list[tuple[int, ToolCall]]) -> None:
    """Insert (tool_id, call) pairs into tool_calls_mgs in one round trip."""
    if not rows:
        return
    cur.executemany(
        f'INSERT INTO {db.table(db.tool_call_table)} ("tool_id", "key_id", "user_id", "called_at", "duration_ms", '
        f'"status", "error_message") VALUES (?, ?, ?, ?, ?, ?, ?)',
        [
            (
                tool_id,
                c.key_id,
                c.user_id,
                c.called_at,
                c.duration_ms,
                c.status,
                c.error_message[:ERROR_MESSAGE_MAX] if c.error_message else None,
            )
            for tool_id, c in rows
        ],
    )
