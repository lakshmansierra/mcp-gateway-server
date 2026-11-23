"""Pydantic schemas for client-to-gateway API keys."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class KeyCreate(BaseModel):
    """Body of POST /api/keys.

    all_servers is not sent: admin keys always reach every server that admin added (enabled or disabled), user
    keys only the servers in server_ids, which must be enabled servers added by the user's own admin.
    """

    key_name: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="Unique among your own keys, e.g. 'dev' or 'claude-desktop'",
    )
    server_ids: list[int] = Field(
        default_factory=list,
        description="Users: the servers this key may reach (at least one), from those your admin added. Admins must leave it out: their keys reach every server they added.",
    )

    @field_validator("server_ids")
    @classmethod
    def _unique_positive(cls, v: list[int]) -> list[int]:
        if any(i <= 0 for i in v):
            raise ValueError("server ids must be positive")
        return list(dict.fromkeys(v))  # drop duplicates, keep order


class KeyServersUpdate(BaseModel):
    """Body of PATCH /api/admin/keys/{key_id}/servers: servers to give the key and servers to take away."""

    add: list[int] = Field(default_factory=list, description="Server ids to add (must be enabled and not deleted)")
    remove: list[int] = Field(default_factory=list, description="Server ids to remove")

    @field_validator("add", "remove")
    @classmethod
    def _unique_positive(cls, v: list[int]) -> list[int]:
        if any(i <= 0 for i in v):
            raise ValueError("server ids must be positive")
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _sensible(self) -> KeyServersUpdate:
        if not self.add and not self.remove:
            raise ValueError("give server ids to add or remove")
        both = sorted(set(self.add) & set(self.remove))
        if both:
            raise ValueError(f"server ids in both add and remove: {both}")
        return self


class KeyOut(BaseModel):
    """A key as returned by the API (never includes the key or its hash)."""

    id: int
    user_id: int  # the key's owner
    key_name: str
    all_servers: bool
    server_ids: list[int]  # empty when all_servers is true
    created_at: datetime


class KeyServerOut(BaseModel):
    """A server mapped to a key. Deleted and disabled servers are listed too, tagged."""

    id: int
    server_name: str
    enabled: bool
    is_deleted: bool


class KeyListOut(BaseModel):
    """A key in the admin's lists (never the key or its hash): deleted keys are included and tagged with is_deleted."""

    id: int
    user_id: int  # the key's owner
    user_name: str
    owner_type: str  # admin / user
    key_name: str
    all_servers: bool  # admin key: reaches every server its admin added
    servers: list[KeyServerOut]  # user keys: the mapped servers; empty for admin keys
    created_at: datetime
    is_deleted: bool
    deleted_by: int | None
    deleted_at: datetime | None


class KeyDeletedOut(BaseModel):
    """Result of DELETE /api/admin/keys/{key_id}."""

    key: KeyOut
    deleted_by: int
    deleted_at: datetime


class KeyCreatedOut(BaseModel):
    """Result of POST /api/keys and of rotating a key. `api_key` is shown only here; only its hash is stored."""

    id: int
    key_name: str
    api_key: str
    all_servers: bool
    server_ids: list[int]
    created_at: datetime
