"""Backend settings, read from the project's .env (HANA credentials and table names)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# Table and schema names are put into SQL as quoted identifiers, so only allow plain names.
_IDENTIFIER = re.compile(r"[A-Za-z0-9_]+")


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing setting in .env: {name}")
    return value


def _identifier(name: str) -> str:
    value = _required(name)
    if not _IDENTIFIER.fullmatch(value):
        raise RuntimeError(f"{name} may only contain letters, digits and '_'")
    return value


def _jwt_secret() -> str:
    value = _required("JWT_SECRET")
    if len(value) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
    return value


@dataclass(frozen=True)
class Settings:
    hana_host: str
    hana_port: int
    hana_user: str
    hana_password: str
    hana_schema: str
    user_table: str
    server_table: str
    api_key_table: str
    api_key_mapping_table: str
    cors_origins: list[str]
    jwt_secret: str
    jwt_expire_minutes: int
    admin_register_key: str | None  # None = admin registration is switched off

    def table(self, name: str) -> str:
        """Fully qualified, quoted table name, e.g. "SCHEMA"."user_mgs"."""
        return f'"{self.hana_schema}"."{name}"'


@lru_cache
def get_settings() -> Settings:
    load_dotenv(ENV_FILE)
    origins = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        hana_host=_required("HANA_HOST"),
        hana_port=int(_required("HANA_PORT")),
        hana_user=_required("HANA_USER"),
        hana_password=_required("HANA_PASSWORD"),
        hana_schema=_identifier("HANA_SCHEMA"),
        user_table=_identifier("USER_TABLE"),
        server_table=_identifier("MCP_SERVER_TABLE"),
        api_key_table=_identifier("MCP_CLIENT_TO_GATEWAY_API_KEY_TABLE"),
        api_key_mapping_table=_identifier("MCP_CLIENT_TO_GATEWAY_API_KEY_MAPPING_TABLE"),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        jwt_secret=_jwt_secret(),
        jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "480")),
        admin_register_key=os.getenv("ADMIN_REGISTER_KEY", "").strip() or None,
    )
