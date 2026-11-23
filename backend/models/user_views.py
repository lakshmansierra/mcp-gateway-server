"""Pydantic schemas for what a user (not an admin) sees. Nothing deleted or removed ever appears here, and no server
internals (URL, tool filters) are shown."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserServerOut(BaseModel):
    """A server the user may use (added by their admin, enabled, not deleted)."""

    id: int
    server_name: str
    tool_count: int = Field(description="Tools you can call on this server")
    created_at: datetime


class UserToolOut(BaseModel):
    """A tool the user can call: listed by the server now and not hidden by the admin's filters."""

    id: int
    server_id: int
    server_name: str
    tool_name: str = Field(description="The name on the server, e.g. 'add'")
    gateway_name: str = Field(description="The name to call through the gateway, e.g. 'abc__add'")
    description: str | None
    input_schema: Any = Field(description="The tool's JSON schema for its arguments")
    first_seen_at: datetime


class UserKeyServerOut(BaseModel):
    """A server one of the user's keys reaches. A disabled server is listed with enabled = false: the key can't
    reach it until the admin enables it again."""

    id: int
    server_name: str
    enabled: bool


class UserKeyOut(BaseModel):
    """One of the user's live keys (never the key itself; it was shown once, when created)."""

    id: int
    key_name: str
    servers: list[UserKeyServerOut]
    created_at: datetime
