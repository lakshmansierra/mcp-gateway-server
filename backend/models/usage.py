"""Pydantic schemas for tool usage (read-only; the gateway records every tools/call)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CallStatus = Literal["ok", "error", "timeout"]


class Counts(BaseModel):
    calls: int
    ok: int
    error: int
    timeout: int
    avg_duration_ms: float | None
    last_called_at: datetime | None


class ToolUsageOut(Counts):
    tool_id: int
    tool_name: str
    gateway_name: str
    is_removed: bool
    server_id: int
    server_name: str


class ServerUsageOut(Counts):
    server_id: int
    server_name: str


class UserUsageOut(Counts):
    user_id: int
    user_name: str | None
    type: str | None  # admin / user


class UsageSummaryOut(Counts):
    """GET /api/admin/usage. The top-level counts cover every matching call."""

    start: datetime | None = Field(description="Only calls at or after this time (UTC); null = from the beginning")
    end: datetime | None = Field(description="Only calls before this time (UTC); null = until now")
    by_server: list[ServerUsageOut]
    by_tool: list[ToolUsageOut] = Field(description="Every tool of your servers, including tools never called")
    by_user: list[UserUsageOut] = Field(description="Only accounts with at least one matching call")


class KeyUsageOut(Counts):
    key_id: int
    key_name: str | None


class MyUsageSummaryOut(Counts):
    """GET /api/user/usage: your own calls. The top-level counts cover every matching call."""

    start: datetime | None = Field(description="Only calls at or after this time (UTC); null = from the beginning")
    end: datetime | None = Field(description="Only calls before this time (UTC); null = until now")
    by_server: list[ServerUsageOut]
    by_tool: list[ToolUsageOut] = Field(description="Every tool you can call, including tools you never called")
    by_key: list[KeyUsageOut] = Field(description="Only keys with at least one matching call")


class CallOut(BaseModel):
    id: int
    called_at: datetime  # UTC
    server_id: int
    server_name: str
    tool_id: int
    tool_name: str
    gateway_name: str
    key_id: int
    key_name: str | None
    user_id: int
    user_name: str | None
    duration_ms: int
    status: str
    error_message: str | None


class CallPageOut(BaseModel):
    """GET /api/admin/usage/calls: one page of the call log, newest first."""

    total: int = Field(description="Calls matching the filters, across all pages")
    limit: int
    offset: int
    items: list[CallOut]
