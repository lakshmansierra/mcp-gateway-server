"""Gateway configuration. Only these environment variables are read (from mcp_gateway/.env or the real
environment); nothing else is:

    GATEWAY_NAME, GATEWAY_VERSION, GATEWAY_TRANSPORT,
    GATEWAY_HOST, GATEWAY_PORT, GATEWAY_PATH, GATEWAY_ALLOWED_HOSTS     how the gateway presents itself and listens
    GATEWAY_LOG_LEVEL, GATEWAY_AUTH_ENABLED                             logging; require client API keys
    GATEWAY_RECONNECT_INITIAL_DELAY, GATEWAY_RECONNECT_MAX_DELAY,
    GATEWAY_STARTUP_CONNECT_TIMEOUT, GATEWAY_HEALTH_CHECK_INTERVAL,
    GATEWAY_CATALOG_TTL, GATEWAY_CHANGE_DEBOUNCE, GATEWAY_CLIENT_SESSION_IDLE,
    GATEWAY_DB_SYNC_INTERVAL                                            timers (seconds)
    GATEWAY_HEALTH_PATH, GATEWAY_CLIENT_ID_HEADER                       health route; header naming the client to servers
    GATEWAY_RELOAD_PATH, GATEWAY_RELOAD_SECRET                          route the backend calls after a change
    GATEWAY_USAGE_FLUSH_INTERVAL, GATEWAY_USAGE_BUFFER_MAX              tool usage: how often it is written to HANA,
                                                                        how many unwritten rows may wait
    HANA_HOST, HANA_PORT, HANA_USER, HANA_PASSWORD, HANA_SCHEMA         the database
    HANA_CONNECT_TIMEOUT, HANA_QUERY_TIMEOUT                            seconds before a HANA call gives up
    USER_TABLE, MCP_SERVER_TABLE,
    MCP_CLIENT_TO_GATEWAY_API_KEY_TABLE,
    MCP_CLIENT_TO_GATEWAY_API_KEY_MAPPING_TABLE                         the backend's tables
    MCP_SERVER_AUTH_TABLE                                               per-server upstream auth config (the gateway reads it)
    MCP_TOOL_TABLE, MCP_TOOL_CHANGE_TABLE, MCP_TOOL_CALL_TABLE          tool usage tables (the gateway writes them)
    MCP_SERVER_TOKEN_CACHE_TABLE                                        OAuth2 access-token cache (the gateway writes it)

Everything else comes from HANA: the MCP servers and the client API keys are rows in those tables, managed
through the backend, loaded at startup and re-read every GATEWAY_DB_SYNC_INTERVAL seconds (mcp_gateway/db/).
The gateway writes only the tool usage tables: each server's tools and their history, and every tool call
(mcp_gateway/usage/).
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

NAME_SEPARATOR = "__"
ALL_TOOLS = "*"  # in _INCLUDE_TOOLS: expose every tool

LIST_FIELDS = {"include_tools", "exclude_tools", "allowed_hosts"}
GATEWAY_FIELDS = {
    "GATEWAY_NAME": "name",
    "GATEWAY_HOST": "host",
    "GATEWAY_PORT": "port",
    "GATEWAY_PATH": "path",
    "GATEWAY_ALLOWED_HOSTS": "allowed_hosts",
    "GATEWAY_RECONNECT_INITIAL_DELAY": "reconnect_initial_delay",
    "GATEWAY_RECONNECT_MAX_DELAY": "reconnect_max_delay",
    "GATEWAY_LOG_LEVEL": "log_level",
    "GATEWAY_VERSION": "version",
    "GATEWAY_TRANSPORT": "transport",
    "GATEWAY_STARTUP_CONNECT_TIMEOUT": "startup_connect_timeout",
    "GATEWAY_HEALTH_CHECK_INTERVAL": "health_check_interval",
    "GATEWAY_CATALOG_TTL": "catalog_ttl",
    "GATEWAY_CHANGE_DEBOUNCE": "change_debounce",
    "GATEWAY_CLIENT_SESSION_IDLE": "client_session_idle",
    "GATEWAY_DB_SYNC_INTERVAL": "db_sync_interval",
    "GATEWAY_HEALTH_PATH": "health_path",
    "GATEWAY_CLIENT_ID_HEADER": "client_id_header",
    "GATEWAY_RELOAD_PATH": "reload_path",
    "GATEWAY_RELOAD_SECRET": "reload_secret",
    "GATEWAY_USAGE_FLUSH_INTERVAL": "usage_flush_interval",
    "GATEWAY_USAGE_BUFFER_MAX": "usage_buffer_max",
}
DATABASE_FIELDS = {
    "HANA_HOST": "host",
    "HANA_PORT": "port",
    "HANA_USER": "user",
    "HANA_PASSWORD": "password",
    "HANA_SCHEMA": "schema_name",
    "HANA_CONNECT_TIMEOUT": "connect_timeout",
    "HANA_QUERY_TIMEOUT": "query_timeout",
    "USER_TABLE": "user_table",
    "MCP_SERVER_TABLE": "server_table",
    "MCP_CLIENT_TO_GATEWAY_API_KEY_TABLE": "api_key_table",
    "MCP_CLIENT_TO_GATEWAY_API_KEY_MAPPING_TABLE": "api_key_mapping_table",
    "MCP_SERVER_AUTH_TABLE": "server_auth_table",
    "MCP_TOOL_TABLE": "tool_table",
    "MCP_TOOL_CHANGE_TABLE": "tool_change_table",
    "MCP_TOOL_CALL_TABLE": "tool_call_table",
    "MCP_SERVER_TOKEN_CACHE_TABLE": "token_cache_table",
}
# No default can be guessed for these: the gateway stops at startup if one is missing.
REQUIRED_DATABASE_VARS = ("HANA_HOST", "HANA_USER", "HANA_PASSWORD", "HANA_SCHEMA")


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class AuthConfig(BaseModel):
    """How the gateway authenticates to one upstream: a row of the auth table (mcp_server_auth_mgs), keyed by
    the server's id. A server with no row uses no auth. Secrets are stored reversibly (the gateway must present
    them) and kept out of repr/logs.

    Only the columns the chosen auth_type needs are set; the rest are None. For 'oauth2' the gateway fetches a
    short-lived token from token_url at connect time (not yet implemented); 'bearer' and 'basic' are static.
    """

    auth_type: Literal["bearer", "basic", "oauth2"]

    # bearer
    token: str | None = Field(None, repr=False)

    # basic (also the oauth2 'password' grant)
    username: str | None = None
    password: str | None = Field(None, repr=False)

    # oauth2 (client_credentials | password)
    oauth_grant_type: Literal["client_credentials", "password"] | None = None
    add_auth_data_to: Literal["header", "url"] | None = None
    header_prefix: str | None = None
    token_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = Field(None, repr=False)
    scope: str | None = None
    client_authentication: Literal["basic_header", "body"] | None = None

    def static_header(self) -> dict[str, str] | None:
        """The Authorization header that can be built without contacting an auth server: bearer and basic.
        Returns None for oauth2 (its token is fetched at connect time) and when the type's secret is missing."""
        if self.auth_type == "bearer":
            if not self.token:
                return None
            prefix = (self.header_prefix or "Bearer").strip()
            return {"Authorization": f"{prefix} {self.token}".strip()}
        if self.auth_type == "basic":
            if self.username is None and self.password is None:
                return None
            raw = f"{self.username or ''}:{self.password or ''}".encode()
            return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
        return None


class UpstreamConfig(BaseModel):
    """One live MCP server that the gateway proxies to."""

    # All required: each is a column of the server's row in the HANA server table.
    name: str
    url: str
    transport: Literal["streamable_http", "sse"]
    enabled: bool
    timeout_seconds: float = Field(gt=0)
    # Full tool names as the server names them (before prefixing), e.g. "add", not "server_1__add".
    # include_tools may be just "*" for every tool; no other wildcards are accepted.
    include_tools: list[str]
    exclude_tools: list[str]
    # The admin who registered it (the row's user_id). While the server is disabled, only that admin's keys
    # reach it; everyone else's lists and calls skip it.
    owner_id: int | None = None
    # The row's id: the tool usage tables refer to the server by it (tools_mgs.mcp_id). None = not recorded.
    id: int | None = None
    # How the gateway authenticates to this server (the auth table, keyed by id). None = no auth. Part of the
    # connection, so changing it reconnects (see pool._CONNECTION_FIELDS).
    auth: AuthConfig | None = None

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", v):
            raise ValueError("upstream name may only contain letters, digits, '_' and '-'")
        if NAME_SEPARATOR in v:
            raise ValueError(f"upstream name must not contain '{NAME_SEPARATOR}'")
        return v

    @field_validator("include_tools", "exclude_tools")
    @classmethod
    def _full_names(cls, v: list[str], info: ValidationInfo) -> list[str]:
        allowed = {ALL_TOOLS} if info.field_name == "include_tools" else set()
        partial = [t for t in v if t not in allowed and any(c in t for c in "*?[]")]
        if partial:
            hint = " ('*' alone means all tools)" if allowed else ""
            raise ValueError(f"use full tool names, not patterns: {partial}{hint}")
        return v

    def tool_allowed(self, tool_name: str) -> bool:
        if tool_name in self.exclude_tools:
            return False
        return ALL_TOOLS in self.include_tools or tool_name in self.include_tools


class ApiKeyConfig(BaseModel):
    """A client API key: a live row of the key table. Only its SHA-256 hash is known, never the key itself."""

    id: int
    user_id: int  # who owns the key
    # The admin whose servers this key may reach: the key's owner for admin keys, the admin who created the
    # user (user_mgs.created_by) for user keys. None = no admin, so no servers.
    admin_id: int | None = None
    name: str  # "<user_name>/<key_name>": who is calling, in logs and in GATEWAY_CLIENT_ID_HEADER to servers
    key_hash: str = Field(repr=False)
    all_servers: bool  # 1 for admins' keys: every server that admin registered (enabled or not)
    servers: frozenset[str] = frozenset()  # otherwise: the server_names picked for it (the mapping table)

    def can_access(self, server: UpstreamConfig) -> bool:
        """Only servers registered by this key's admin (admin_id); never another admin's.
        Admin keys (all_servers): all of that admin's servers, enabled or disabled.
        User keys: only the servers mapped to the key, and only while they are enabled."""
        if server.owner_id is None or server.owner_id != self.admin_id:
            return False
        if self.all_servers:
            return True
        return server.enabled and server.name in self.servers

    def can_access_name(self, server_name: str) -> bool:
        """For a server that was just removed (its owner is no longer known): only used to decide who gets the
        "lists changed, re-list" notice, which carries no data, so admin keys get it too."""
        return self.all_servers or server_name in self.servers


class GatewaySettings(BaseModel):
    """Gateway-wide settings. Each reads GATEWAY_<NAME> from .env; the value here is only the fallback."""

    name: str = "mcp-gateway"
    version: str = "1.0.0"  # reported to clients and to servers
    transport: Literal["http", "stdio"] = "http"  # the --transport flag overrides it
    host: str = "127.0.0.1"
    port: int = 8080
    path: str = "/mcp"
    # Hostnames clients use to reach the gateway (DNS-rebinding protection). Empty = allow any.
    allowed_hosts: list[str] = Field(default_factory=list)
    reconnect_initial_delay: float = Field(1.0, gt=0)
    reconnect_max_delay: float = Field(60.0, gt=0)
    log_level: str = "INFO"
    # Seconds. At startup, how long to wait for servers before accepting clients.
    startup_connect_timeout: float = Field(10.0, ge=0)
    # Seconds. How often each server is health-checked (and re-listed, if it can't stream changes).
    health_check_interval: float = Field(30.0, gt=0)
    # Seconds. How old the catalog may get before a list request re-fetches it.
    catalog_ttl: float = Field(30.0, ge=0)
    # Seconds. Wait after a change notification so a burst of changes becomes one refresh.
    change_debounce: float = Field(1.0, ge=0)
    # Seconds. A client's own session to a server closes after this long unused.
    client_session_idle: float = Field(300.0, gt=0)
    # Seconds. How often the server and key tables are re-read, so servers and keys added, edited or deleted
    # in the backend take effect without restarting the gateway.
    db_sync_interval: float = Field(30.0, gt=0)
    # Route that answers without an API key, for load balancers and Cloud Foundry health checks.
    health_path: str = "/health"
    # Header the gateway adds to each client's own session to a server, naming the client ("<user>/<key>").
    client_id_header: str = "X-MCP-Client"
    # The backend calls POST <reload_path> (Authorization: Bearer <reload_secret>) right after it changes a
    # server, key or user, so the gateway re-reads HANA at once instead of at the next db_sync_interval.
    # No secret (the default) = the route is off and only the periodic re-read applies changes.
    reload_path: str = "/internal/reload"
    reload_secret: str | None = Field(None, repr=False)
    # Tool usage (every server's tools and their history, every tool call) is kept in memory and written to
    # HANA in the background every usage_flush_interval seconds, so calls never wait for the database. While
    # HANA can't be reached, up to usage_buffer_max calls wait; beyond that the oldest are dropped (logged).
    usage_flush_interval: float = Field(5.0, gt=0)
    usage_buffer_max: int = Field(10000, gt=0)

    @field_validator("path", "health_path", "reload_path")
    @classmethod
    def _absolute_path(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("must start with '/'")
        return v

    @field_validator("client_id_header")
    @classmethod
    def _header_name(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9-]+", v):
            raise ValueError("may only contain letters, digits and '-'")
        return v


class DatabaseSettings(BaseModel):
    """Where the MCP servers and client API keys live: the backend's tables in SAP HANA. host, user, password
    and schema_name are required; the rest read .env too and fall back to the values here."""

    host: str
    port: int = 443  # HANA Cloud's SQL port
    user: str
    password: str = Field(repr=False)
    schema_name: str
    # Seconds. Without them a dead network could block a read forever, and the gateway would stop re-reading
    # servers and keys (deleted keys would keep working). With them a stuck call fails and the next round retries.
    connect_timeout: float = Field(10.0, gt=0)
    query_timeout: float = Field(30.0, gt=0)
    user_table: str = "user_mgs"
    server_table: str = "mcp_app_mgs"
    api_key_table: str = "client_to_gateway_mcp_api_key_mgs"
    api_key_mapping_table: str = "client_to_gateway_mcp_api_key_mapping_mgs"
    # Per-server auth config (bearer/basic/oauth2), written by the backend and read by the gateway.
    server_auth_table: str = "mcp_server_auth_mgs"
    # Written by the gateway: each server's tools, their history, and every tool call.
    tool_table: str = "tools_mgs"
    tool_change_table: str = "tool_changes_mgs"
    tool_call_table: str = "tool_calls_mgs"
    # Written by the gateway: OAuth2 access tokens it fetches, cached with their expiry.
    token_cache_table: str = "mcp_server_token_cache_mgs"

    @field_validator(
        "schema_name",
        "user_table",
        "server_table",
        "api_key_table",
        "api_key_mapping_table",
        "server_auth_table",
        "tool_table",
        "tool_change_table",
        "tool_call_table",
        "token_cache_table",
    )
    @classmethod
    def _plain_identifier(cls, v: str) -> str:
        # Put into SQL as quoted identifiers, so only plain names are allowed.
        if not re.fullmatch(r"[A-Za-z0-9_]+", v):
            raise ValueError("may only contain letters, digits and '_'")
        return v

    def table(self, name: str) -> str:
        """Fully qualified, quoted table name, e.g. "SCHEMA"."mcp_app_mgs"."""
        return f'"{self.schema_name}"."{name}"'


class AuthSettings(BaseModel):
    enabled: bool = True  # GATEWAY_AUTH_ENABLED; this is only the fallback
    # The keys themselves come from HANA (mcp_gateway/db/api_keys.py) and change while the gateway runs.


class GatewayConfig(BaseModel):
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    database: DatabaseSettings
    upstreams: list[UpstreamConfig] = Field(default_factory=list)  # filled from the server table at startup
    api_keys: list[ApiKeyConfig] = Field(default_factory=list)  # filled from the key table at startup

    @field_validator("upstreams")
    @classmethod
    def _unique_names(cls, v: list[UpstreamConfig]) -> list[UpstreamConfig]:
        names = [u.name for u in v]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate upstream names: {sorted(dupes)}")
        return v



def load_config(env: Mapping[str, str] | None = None) -> GatewayConfig:
    """Build the config from environment variables (defaults to os.environ). The servers and API keys are
    loaded separately, from HANA (mcp_gateway/db/)."""
    env = os.environ if env is None else env
    gateway = {
        field_name: _split_list(env[var]) if field_name in LIST_FIELDS else env[var]
        for var, field_name in GATEWAY_FIELDS.items()
        if env.get(var, "") != ""
    }
    missing = [var for var in REQUIRED_DATABASE_VARS if env.get(var, "").strip() == ""]
    if missing:
        raise ValueError(f"Missing database settings in .env: {', '.join(missing)}")
    database = {
        field_name: env[var].strip() for var, field_name in DATABASE_FIELDS.items() if env.get(var, "").strip() != ""
    }
    auth: dict[str, Any] = {}
    if env.get("GATEWAY_AUTH_ENABLED", "") != "":
        auth["enabled"] = env["GATEWAY_AUTH_ENABLED"]
    return GatewayConfig.model_validate({"gateway": gateway, "auth": auth, "database": database})
