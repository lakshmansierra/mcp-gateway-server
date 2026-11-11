"""Gateway configuration, read from environment variables (optionally loaded from a .env file).

    GATEWAY_HOST, GATEWAY_PORT, ...           gateway settings
    API_KEY_<NAME>=<secret>                     a client API key for every server
    API_KEY_<NAME>_SERVERS=server_1,server_2    restrict that key to some MCP servers

Every MCP server behind the gateway needs all of these (they mirror the server table's columns,
so the code holds no per-server defaults):
    SERVER_<ID>_URL=https://...                 where the server is
    SERVER_<ID>_TRANSPORT=streamable_http       or sse
    SERVER_<ID>_TIMEOUT=60                      seconds to wait for each reply
    SERVER_<ID>_ENABLED=true                    false = don't connect
    SERVER_<ID>_INCLUDE_TOOLS=*                 full tool names to expose, comma-separated; * = all
    SERVER_<ID>_EXCLUDE_TOOLS=delete_everything full tool names to hide from those (may be empty)

SERVER_<ID> lowercased is the server's name and tool prefix, e.g. SERVER_1_URL -> "server_1" -> server_1__add.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from fnmatch import fnmatch
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

logger = logging.getLogger(__name__)

NAME_SEPARATOR = "__"
ALL_TOOLS = "*"  # in _INCLUDE_TOOLS: expose every tool

SERVER_PREFIX = "SERVER_"
API_KEY_PREFIX = "API_KEY_"
# Per-server setting suffixes -> UpstreamConfig field. Longest first so _INCLUDE_TOOLS wins over shorter matches.
UPSTREAM_FIELDS = {
    "_INCLUDE_TOOLS": "include_tools",
    "_EXCLUDE_TOOLS": "exclude_tools",
    "_TRANSPORT": "transport",
    "_ENABLED": "enabled",
    "_TIMEOUT": "timeout_seconds",
    "_URL": "url",
}
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
}


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class UpstreamConfig(BaseModel):
    """One live MCP server that the gateway proxies to."""

    # All required: each comes from SERVER_<ID>_<SETTING> in .env (later, a row in the server table).
    name: str
    url: str
    transport: Literal["streamable_http", "sse"]
    enabled: bool
    timeout_seconds: float = Field(gt=0)
    # Full tool names as the server names them (before prefixing), e.g. "add", not "server_1__add".
    # include_tools may be just "*" for every tool; no other wildcards are accepted.
    include_tools: list[str]
    exclude_tools: list[str]

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
    """A client credential. `upstreams` restricts which upstreams this key may reach."""

    name: str
    key: str
    upstreams: list[str] = Field(default_factory=lambda: ["*"])

    def can_access(self, upstream: str) -> bool:
        return any(fnmatch(upstream, p) for p in self.upstreams)


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


class AuthSettings(BaseModel):
    enabled: bool = True  # GATEWAY_AUTH_ENABLED; this is only the fallback
    api_keys: list[ApiKeyConfig] = Field(default_factory=list)

    @field_validator("api_keys")
    @classmethod
    def _unique_secrets(cls, v: list[ApiKeyConfig]) -> list[ApiKeyConfig]:
        # The secret alone identifies the caller, so two keys sharing one would make access ambiguous.
        secrets = [k.key for k in v]
        dupes = sorted({k.name for k in v if secrets.count(k.key) > 1})
        if dupes:
            raise ValueError(f"API keys {dupes} use the same secret; every key needs its own value")
        return v


class GatewayConfig(BaseModel):
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    upstreams: list[UpstreamConfig] = Field(default_factory=list)

    @field_validator("upstreams")
    @classmethod
    def _unique_names(cls, v: list[UpstreamConfig]) -> list[UpstreamConfig]:
        names = [u.name for u in v]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate upstream names: {sorted(dupes)}")
        return v

    @property
    def enabled_upstreams(self) -> list[UpstreamConfig]:
        return [u for u in self.upstreams if u.enabled]


def _parse_upstreams(env: Mapping[str, str]) -> list[dict[str, Any]]:
    upstreams: dict[str, dict[str, Any]] = {}
    for var, value in env.items():
        if not var.startswith(SERVER_PREFIX):
            continue
        for suffix, field_name in UPSTREAM_FIELDS.items():
            if var.endswith(suffix) and len(var) > len(SERVER_PREFIX) + len(suffix):
                name = var[: -len(suffix)].lower()
                entry = upstreams.setdefault(name, {"name": name})
                entry[field_name] = _split_list(value) if field_name in LIST_FIELDS else value
                break
        else:
            # Other software may set SERVER_* variables (e.g. SERVER_NAME), so skip rather than fail.
            logger.warning("Ignoring '%s': expected SERVER_<ID>_URL, _TRANSPORT, _TIMEOUT, ...", var)

    missing = [
        f"{name.upper()}{suffix}"
        for name, entry in sorted(upstreams.items())
        for suffix, field_name in UPSTREAM_FIELDS.items()
        if field_name not in entry
    ]
    if missing:
        raise ValueError(f"Missing server settings in .env: {', '.join(missing)}")
    return sorted(upstreams.values(), key=lambda u: u["name"])


def _parse_api_keys(env: Mapping[str, str]) -> list[dict[str, Any]]:
    keys: dict[str, dict[str, Any]] = {}
    for var, value in env.items():
        if not var.startswith(API_KEY_PREFIX):
            continue
        rest = var[len(API_KEY_PREFIX) :]
        if rest.endswith("_SERVERS"):
            name = rest[: -len("_SERVERS")].lower()
            keys.setdefault(name, {"name": name})["upstreams"] = _split_list(value)
        else:
            keys.setdefault(rest.lower(), {"name": rest.lower()})["key"] = value

    missing = sorted(name for name, entry in keys.items() if not entry.get("key"))
    if missing:
        raise ValueError(f"API key(s) {missing} have _SERVERS set but no API_KEY_<NAME> secret")
    return sorted(keys.values(), key=lambda k: k["name"])


def load_config(env: Mapping[str, str] | None = None) -> GatewayConfig:
    """Build the config from environment variables (defaults to os.environ)."""
    env = os.environ if env is None else env
    gateway = {
        field_name: _split_list(env[var]) if field_name in LIST_FIELDS else env[var]
        for var, field_name in GATEWAY_FIELDS.items()
        if env.get(var, "") != ""
    }
    upstreams = _parse_upstreams(env)
    auth: dict[str, Any] = {"api_keys": _parse_api_keys(env)}
    if env.get("GATEWAY_AUTH_ENABLED", "") != "":
        auth["enabled"] = env["GATEWAY_AUTH_ENABLED"]
    return GatewayConfig.model_validate({"gateway": gateway, "auth": auth, "upstreams": upstreams})
