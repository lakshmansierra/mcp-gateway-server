"""Pydantic schemas for the tools of MCP servers and their history (read-only; the gateway records them)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolOut(BaseModel):
    """A tool a server lists, or once listed (is_removed)."""

    id: int
    server_id: int
    server_name: str
    tool_name: str = Field(description="The name on the server, e.g. 'add'")
    gateway_name: str = Field(description="The name clients see through the gateway, e.g. 'abc__add'")
    description: str | None
    input_schema: Any = Field(description="The tool's JSON schema for its arguments")
    first_seen_at: datetime
    is_removed: bool = Field(description="The server no longer lists this tool")
    removed_at: datetime | None
    hidden: bool = Field(description="The server's include_tools / exclude_tools keep it from clients")
    server_enabled: bool
    server_is_deleted: bool


class ToolChangeOut(BaseModel):
    """One entry of a tool's history. old_value / new_value: {"description": ..., "input_schema": ...}."""

    id: int
    tool_id: int
    change_type: str = Field(description="added / removed / changed")
    changed_at: datetime
    old_value: Any
    new_value: Any
