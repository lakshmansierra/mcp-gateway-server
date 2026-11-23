"""Pydantic schemas for MCP servers (the server table).

The rules match what the gateway accepts (mcp_gateway/config/settings.py), so every saved server is one the gateway can load.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator

NAME_SEPARATOR = "__"  # the gateway joins server and tool names with this: abc__add
ALL_TOOLS = "*"
WILDCARDS = set("*?[]")
SERVER_NAME_PATTERN = r"^[A-Za-z0-9_-]+$"

Transport = Literal["streamable_http", "sse"]


def _check_server_name(v: str) -> str:
    if NAME_SEPARATOR in v:
        raise ValueError(f"server_name must not contain '{NAME_SEPARATOR}'")
    return v


def _clean_names(names: list[str]) -> list[str]:
    """Strip spaces, drop blanks and duplicates, keep order."""
    seen: dict[str, None] = {}
    for n in names:
        if n.strip():
            seen.setdefault(n.strip(), None)
    return list(seen)


def _full_names_only(names: list[str]) -> list[str]:
    patterns = [n for n in names if WILDCARDS & set(n)]
    if patterns:
        raise ValueError(f"use full tool names, not patterns: {patterns}")
    with_commas = [n for n in names if "," in n]
    if with_commas:
        raise ValueError(f"tool names cannot contain commas: {with_commas}")
    return names


class ServerCreate(BaseModel):
    """Body of POST /api/admin/servers.

    Tool filters are not part of it: when a server is added its tool names aren't known yet, so the table's
    defaults apply (include_tools = '*', every tool; exclude_tools = NULL, none hidden).
    """

    server_name: str = Field(
        min_length=1,
        max_length=100,
        pattern=SERVER_NAME_PATTERN,
        description="Becomes the tool prefix: server 'abc' exposes 'abc__add'",
    )
    server_url: AnyHttpUrl = Field(description="The server's live MCP URL, e.g. https://host/mcp or .../sse")
    transport: Transport = "streamable_http"
    timeout_seconds: int = Field(60, gt=0, le=3600)
    enabled: bool = True

    @field_validator("server_name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _check_server_name(v)


class ServerUpdate(BaseModel):
    """Body of PATCH /api/admin/servers/{server_id}. Send only the fields to change.

    include_tools: full tool names, or ["*"] for every tool.
    exclude_tools: full tool names to hide from the included ones; [] or null hides none.
    """

    server_name: str | None = Field(None, min_length=1, max_length=100, pattern=SERVER_NAME_PATTERN)
    server_url: AnyHttpUrl | None = None
    transport: Transport | None = None
    timeout_seconds: int | None = Field(None, gt=0, le=3600)
    enabled: bool | None = None
    include_tools: list[str] | None = None
    exclude_tools: list[str] | None = None

    @field_validator("server_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return None if v is None else _check_server_name(v)

    @field_validator("include_tools")
    @classmethod
    def _include(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        names = _clean_names(v)
        if not names:
            raise ValueError('give at least one tool name, or ["*"] for every tool')
        if ALL_TOOLS in names:
            return [ALL_TOOLS]  # "*" already covers every tool
        return _full_names_only(names)

    @field_validator("exclude_tools")
    @classmethod
    def _exclude(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _full_names_only(_clean_names(v))

    @model_validator(mode="after")
    def _something_to_change(self) -> ServerUpdate:
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        # Only exclude_tools may be cleared with null; the other columns always need a value.
        nulls = sorted(f for f in self.model_fields_set if getattr(self, f) is None and f != "exclude_tools")
        if nulls:
            raise ValueError(f"these fields cannot be null: {nulls}")
        return self

    def changes(self) -> dict[str, object]:
        """Column -> value for the fields that were sent, in the form the table stores them."""
        out: dict[str, object] = {}
        for field in self.model_fields_set:
            value = getattr(self, field)
            if field == "server_url":
                value = str(value)
            elif field == "enabled":
                value = int(value)
            elif field in ("include_tools", "exclude_tools"):
                value = ",".join(value or []) or None  # an empty exclude list is stored as NULL
            out[field] = value
        return out


class ServerOut(BaseModel):
    """A registered MCP server as returned by the API."""

    id: int
    user_id: int  # the admin who registered it
    server_name: str
    server_url: str
    transport: str
    timeout_seconds: int
    enabled: bool
    include_tools: list[str]
    exclude_tools: list[str]
    created_at: datetime


class ServerListOut(ServerOut):
    """A server in the admin's lists: deleted servers are included and tagged with is_deleted."""

    is_deleted: bool
    deleted_by: int | None
    deleted_at: datetime | None
    tool_count: int = Field(description="Tools the server lists now, as the gateway last saw them (hidden ones too)")


class ServerDeletedOut(BaseModel):
    """Result of DELETE /api/admin/servers/{server_id}."""

    server: ServerOut
    deleted_by: int
    deleted_at: datetime


def split_tools(value: str | None) -> list[str]:
    """DB text ('add,multiply') -> list (['add', 'multiply'])."""
    return [t.strip() for t in (value or "").split(",") if t.strip()]
