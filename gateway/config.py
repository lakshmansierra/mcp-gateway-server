"""Gateway configuration, read from environment variables (optionally loaded from a .env file).

    GATEWAY_HOST, GATEWAY_PORT, ...           gateway settings
    API_KEY_<NAME>=<secret>                     a client API key
    API_KEY_<NAME>_SERVERS=server_1,server_2    restrict that key to some MCP servers
    SERVER_<ID>_URL=https://...                 an MCP server behind the gateway
    SERVER_<ID>_HEADER_<HEADER>=value           a header sent to it (`_` in <HEADER> becomes `-`)

SERVER_<ID> lowercased is the server's name and tool prefix, e.g. SERVER_1_URL -> "server_1" -> server_1__add.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from fnmatch import fnmatch
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

NAME_SEPARATOR = "__"

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
HEADER_MARKER = "_HEADER_"
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
}


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class UpstreamConfig(BaseModel):
    """One live MCP server that the gateway proxies to."""

    name: str
    url: str
    transport: Literal["streamable_http", "sse"] = "streamable_http"
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: float = 60.0
    # Glob patterns on the upstream's own tool names (before prefixing).
    include_tools: list[str] = Field(default_factory=lambda: ["*"])
    exclude_tools: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", v):
            raise ValueError("upstream name may only contain letters, digits, '_' and '-'")
        if NAME_SEPARATOR in v:
            raise ValueError(f"upstream name must not contain '{NAME_SEPARATOR}'")
        return v

    def tool_allowed(self, tool_name: str) -> bool:
        if any(fnmatch(tool_name, p) for p in self.exclude_tools):
            return False
        return any(fnmatch(tool_name, p) for p in self.include_tools)


class ApiKeyConfig(BaseModel):
    """A client credential. `upstreams` restricts which upstreams this key may reach."""

    name: str
    key: str
    upstreams: list[str] = Field(default_factory=lambda: ["*"])

    def can_access(self, upstream: str) -> bool:
        return any(fnmatch(upstream, p) for p in self.upstreams)


class GatewaySettings(BaseModel):
    name: str = "mcp-gateway"
    host: str = "127.0.0.1"
    port: int = 8080
    path: str = "/mcp"
    # Hostnames clients use to reach the gateway (DNS-rebinding protection). Empty = allow any.
    allowed_hosts: list[str] = Field(default_factory=list)
    reconnect_initial_delay: float = 1.0
    reconnect_max_delay: float = 60.0
    log_level: str = "INFO"


class AuthSettings(BaseModel):
    enabled: bool = True
    api_keys: list[ApiKeyConfig] = Field(default_factory=list)


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
        if HEADER_MARKER in var:
            server, header = var.split(HEADER_MARKER, 1)
            entry = upstreams.setdefault(server.lower(), {"name": server.lower()})
            entry.setdefault("headers", {})[header.replace("_", "-")] = value
            continue
        for suffix, field_name in UPSTREAM_FIELDS.items():
            if var.endswith(suffix) and len(var) > len(SERVER_PREFIX) + len(suffix):
                name = var[: -len(suffix)].lower()
                entry = upstreams.setdefault(name, {"name": name})
                entry[field_name] = _split_list(value) if field_name in LIST_FIELDS else value
                break
        else:
            # Other software may set SERVER_* variables (e.g. SERVER_NAME), so skip rather than fail.
            logger.warning("Ignoring '%s': expected SERVER_<ID>_URL, _TRANSPORT, _HEADER_<X>, ...", var)

    missing = sorted(name for name, entry in upstreams.items() if "url" not in entry)
    if missing:
        raise ValueError(f"Server(s) {missing} have settings but no SERVER_<ID>_URL")
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
    auth: dict[str, Any] = {"api_keys": _parse_api_keys(env)}
    if env.get("GATEWAY_AUTH_ENABLED", "") != "":
        auth["enabled"] = env["GATEWAY_AUTH_ENABLED"]
    return GatewayConfig.model_validate({"gateway": gateway, "auth": auth, "upstreams": _parse_upstreams(env)})
