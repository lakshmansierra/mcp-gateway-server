"""Record tool usage without slowing anything down.

The gateway reports two things here, both from the event loop and both instant (they only touch memory):
  tools_listed  a server's full tool list, after each successful re-list (connect, every health check, push)
  call_made     one finished tools/call

`run` writes them to HANA every GATEWAY_USAGE_FLUSH_INTERVAL seconds, in a worker thread (mcp_gateway/db/usage.py).
If HANA can't be reached, everything waits for the next round: the latest tool list per server, and up to
GATEWAY_USAGE_BUFFER_MAX calls (beyond that the oldest calls are dropped, with a warning). Calls keep working.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Iterable
from datetime import datetime, timezone

import anyio
import mcp_types as types
from hdbcli import dbapi

from mcp_gateway.config.settings import DatabaseSettings, GatewaySettings
from mcp_gateway.db.connection import connect
from mcp_gateway.db.usage import ToolCall, ToolInfo, insert_calls, sync_tools, tool_ids

logger = logging.getLogger(__name__)

PendingTools = dict[int, tuple[str, list[ToolInfo]]]  # mcp_id -> (server name, its latest tool list)


def utc_now() -> datetime:
    """Naive UTC, like CURRENT_TIMESTAMP on HANA Cloud."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def tool_info(tool: types.Tool) -> ToolInfo:
    schema = json.dumps(tool.input_schema, sort_keys=True) if tool.input_schema is not None else None
    return ToolInfo(name=tool.name, description=tool.description, input_schema=schema)


class UsageRecorder:
    def __init__(self, db: DatabaseSettings, settings: GatewaySettings) -> None:
        self._db = db
        self._settings = settings
        self._tools: PendingTools = {}
        self._calls: deque[ToolCall] = deque()
        self._dropped = 0

    # ---- reported by the gateway (event loop; memory only) ------------------

    def tools_listed(self, mcp_id: int, server_name: str, tools: Iterable[types.Tool]) -> None:
        """A server's full tool list (before include/exclude filtering), to be compared with tools_mgs. Only the
        latest list per server is kept: an older one waiting to be written has nothing the newer lacks."""
        self._tools[mcp_id] = (server_name, [tool_info(t) for t in tools])

    def call_made(self, call: ToolCall) -> None:
        self._calls.append(call)
        self._trim()

    def _trim(self) -> None:
        while len(self._calls) > self._settings.usage_buffer_max:
            self._calls.popleft()
            self._dropped += 1

    # ---- writing to HANA -------------------------------------------------------

    async def run(self) -> None:
        """Write what was reported every usage_flush_interval seconds; on shutdown, write what is left."""
        try:
            while True:
                await anyio.sleep(self._settings.usage_flush_interval)
                await self.flush()
        finally:
            with anyio.CancelScope(shield=True), anyio.move_on_after(self._db.connect_timeout + self._db.query_timeout):
                await self.flush()

    async def flush(self) -> None:
        tools, self._tools = self._tools, {}
        calls = list(self._calls)
        self._calls.clear()
        if tools or calls:
            try:
                failed_tools, retry_calls = await anyio.to_thread.run_sync(
                    self._write, tools, calls, abandon_on_cancel=True
                )
            except Exception as exc:  # noqa: BLE001 - HANA unreachable, ...: keep everything for the next round
                logger.warning("Could not write tool usage to HANA (retrying next round): %s", exc)
                failed_tools, retry_calls = tools, calls
            self._put_back(failed_tools, retry_calls)
        if self._dropped:
            logger.warning(
                "Dropped %d tool calls without recording them: more than GATEWAY_USAGE_BUFFER_MAX (%d) were waiting "
                "for HANA",
                self._dropped,
                self._settings.usage_buffer_max,
            )
            self._dropped = 0

    def _put_back(self, tools: PendingTools, calls: list[ToolCall]) -> None:
        for mcp_id, pending in tools.items():
            self._tools.setdefault(mcp_id, pending)  # a list reported meanwhile is newer: it wins
        self._calls.extendleft(reversed(calls))  # older than anything reported meanwhile: back in front
        self._trim()

    def _write(self, tools: PendingTools, calls: list[ToolCall]) -> tuple[PendingTools, list[ToolCall]]:
        """Runs in a worker thread. Returns what must be retried next round."""
        db = self._db
        conn = connect(db)
        try:
            conn.setautocommit(False)
            cur = conn.cursor()
            failed: PendingTools = {}
            for mcp_id, (server_name, infos) in tools.items():
                try:
                    result = sync_tools(cur, db, mcp_id, infos)
                    conn.commit()
                except dbapi.Error as exc:
                    conn.rollback()
                    failed[mcp_id] = (server_name, infos)
                    logger.warning("Could not record the tools of '%s' (retrying next round): %s", server_name, exc)
                    continue
                if result:
                    logger.info(
                        "Tools of '%s' changed: %d added, %d removed, %d changed",
                        server_name,
                        result.added,
                        result.removed,
                        result.changed,
                    )
            return failed, self._write_calls(conn, cur, calls, failed)
        finally:
            conn.close()

    def _write_calls(
        self, conn: dbapi.Connection, cur: dbapi.Cursor, calls: list[ToolCall], failed_tools: PendingTools
    ) -> list[ToolCall]:
        if not calls:
            return []
        db = self._db
        ids = tool_ids(cur, db, {c.mcp_id for c in calls})
        rows: list[tuple[int, ToolCall]] = []
        retry: list[ToolCall] = []
        unknown = 0
        for call in calls:
            tool_id = ids.get((call.mcp_id, call.tool_name))
            if tool_id is not None:
                rows.append((tool_id, call))
            elif call.mcp_id in failed_tools:
                retry.append(call)  # its server's tools weren't written yet: next round
            else:
                unknown += 1  # a tool the server never listed (the call itself failed on the server)
        if unknown:
            logger.warning("%d tool calls not recorded: the server never listed those tools", unknown)
        try:
            insert_calls(cur, db, rows)
            conn.commit()
        except dbapi.IntegrityError:
            # One bad row (e.g. a key or user row that no longer exists) must not block the rest: insert one by
            # one and drop only the rows HANA refuses.
            conn.rollback()
            for row in rows:
                try:
                    insert_calls(cur, db, [row])
                    conn.commit()
                except dbapi.IntegrityError as exc:
                    conn.rollback()
                    call = row[1]
                    logger.warning(
                        "Dropped a call of tool '%s' (server id %d) that HANA refused: %s", call.tool_name, call.mcp_id, exc
                    )
        return retry
