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

# How the gateway authenticates to the upstream. 'none' means no auth (and removes any stored config).
AuthType = Literal["none", "bearer", "basic", "oauth2"]
OAuthGrant = Literal["client_credentials", "password"]
AddAuthTo = Literal["header", "url"]
ClientAuth = Literal["basic_header", "body"]

# Secret columns: never returned by any GET, only written. The rest of an auth config is echoed back.
_SECRET_FIELDS = ("token", "password", "client_secret")


class AuthIn(BaseModel):
    """Auth config sent with ServerCreate / ServerUpdate: one block per server. Only the fields the chosen
    auth_type needs are required; the rest are ignored. 'none' clears any existing config.

    Secrets (token / password / client_secret) are write-only: send them to set or change them; no GET ever
    returns them. On edit the UI sends a full auth block only when the admin changes auth, so a plain token is
    always present when it's being set — the backend stores a full replacement, it does not merge.
    """

    auth_type: AuthType

    # bearer
    token: str | None = None
    header_prefix: str | None = None  # defaults to 'Bearer' when omitted

    # basic (also the oauth2 'password' grant)
    username: str | None = None
    password: str | None = None

    # oauth2 (client_credentials | password)
    oauth_grant_type: OAuthGrant | None = None
    add_auth_data_to: AddAuthTo | None = None
    token_url: AnyHttpUrl | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scope: str | None = None
    client_authentication: ClientAuth | None = None

    @model_validator(mode="after")
    def _required_per_type(self) -> AuthIn:
        t = self.auth_type
        missing: list[str] = []
        if t == "bearer":
            if not (self.token or "").strip():
                missing.append("token")
        elif t == "basic":
            if not (self.username or "").strip():
                missing.append("username")
        elif t == "oauth2":
            if not self.oauth_grant_type:
                missing.append("oauth_grant_type")
            if not self.token_url:
                missing.append("token_url")
            if not (self.client_id or "").strip():
                missing.append("client_id")
            if not (self.client_secret or "").strip():
                missing.append("client_secret")
            if self.oauth_grant_type == "password":
                if not (self.username or "").strip():
                    missing.append("username")
                if not (self.password or "").strip():
                    missing.append("password")
        if missing:
            raise ValueError(f"{t} auth needs: {', '.join(missing)}")
        return self

    def columns(self) -> dict[str, object]:
        """The mcp_server_auth_mgs columns to store for this config (auth_type != 'none'). Unused columns are
        None; defaults are filled in so the gateway reads a complete row."""
        if self.auth_type == "none":
            return {}
        row: dict[str, object] = {
            "auth_type": self.auth_type,
            "token": None,
            "username": None,
            "password": None,
            "oauth_grant_type": None,
            "add_auth_data_to": None,
            "header_prefix": None,
            "token_url": None,
            "client_id": None,
            "client_secret": None,
            "scope": None,
            "client_authentication": None,
        }
        if self.auth_type == "bearer":
            row["token"] = self.token
            row["header_prefix"] = (self.header_prefix or "Bearer").strip()
        elif self.auth_type == "basic":
            row["username"] = self.username
            row["password"] = self.password or ""
        elif self.auth_type == "oauth2":
            row["oauth_grant_type"] = self.oauth_grant_type
            row["add_auth_data_to"] = self.add_auth_data_to or "header"
            row["header_prefix"] = (self.header_prefix or "Bearer").strip()
            row["token_url"] = str(self.token_url)
            row["client_id"] = self.client_id
            row["client_secret"] = self.client_secret
            row["scope"] = (self.scope or "").strip() or None
            row["client_authentication"] = self.client_authentication or "basic_header"
            if self.oauth_grant_type == "password":
                row["username"] = self.username
                row["password"] = self.password
        return row


class AuthStatusOut(BaseModel):
    """What a GET reports about a server's auth: the type, the non-secret fields, and which secrets are set.
    Never includes token / password / client_secret."""

    auth_type: AuthType = "none"
    header_prefix: str | None = None
    username: str | None = None
    oauth_grant_type: str | None = None
    add_auth_data_to: str | None = None
    token_url: str | None = None
    client_id: str | None = None
    scope: str | None = None
    client_authentication: str | None = None
    has_token: bool = False
    has_password: bool = False
    has_client_secret: bool = False


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
    # How the gateway authenticates to this upstream. Omitted or 'none' means no auth.
    auth: AuthIn | None = None

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
    # Replace the server's auth config. 'none' removes it. Omitted (null) leaves it unchanged.
    auth: AuthIn | None = None

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
        # exclude_tools and auth may be cleared with null; the other columns always need a value.
        nulls = sorted(
            f for f in self.model_fields_set if getattr(self, f) is None and f not in ("exclude_tools", "auth")
        )
        if nulls:
            raise ValueError(f"these fields cannot be null: {nulls}")
        return self

    def changes(self) -> dict[str, object]:
        """Column -> value for the server-table fields that were sent (auth is handled separately)."""
        out: dict[str, object] = {}
        for field in self.model_fields_set:
            if field == "auth":
                continue
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
    auth: AuthStatusOut = Field(default_factory=AuthStatusOut, description="Auth config (type + which secrets are set; never the secrets)")


class ServerDeletedOut(BaseModel):
    """Result of DELETE /api/admin/servers/{server_id}."""

    server: ServerOut
    deleted_by: int
    deleted_at: datetime


def split_tools(value: str | None) -> list[str]:
    """DB text ('add,multiply') -> list (['add', 'multiply'])."""
    return [t.strip() for t in (value or "").split(",") if t.strip()]
