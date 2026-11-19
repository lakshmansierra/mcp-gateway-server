"""Client-to-gateway API keys.

POST   /api/keys                          create a key (any logged-in admin or user). Admin keys reach every
                                          server (all_servers = 1); user keys only the servers in server_ids
                                          (all_servers = 0). The plain key is returned once.
DELETE /api/admin/keys/{key_id}           soft-delete a key (logged-in admin only)
POST   /api/admin/keys/{key_id}/restore   undo a key's soft delete (logged-in admin only)
PATCH  /api/admin/keys/{key_id}/servers   add / remove servers on a key (logged-in admin only)
POST   /api/admin/keys/{key_id}/rotate    new value for a key, same name and servers (logged-in admin only)
                                          All four: only keys you created, or that users you created created.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from hdbcli import dbapi

from backend.auth import current_admin, current_user
from backend.db import get_db
from backend.models import KeyCreate, KeyCreatedOut, KeyDeletedOut, KeyOut, KeyServersUpdate, UserOut
from backend.services import api_keys as key_service

router = APIRouter(prefix="/api/keys", tags=["api keys"])
admin_router = APIRouter(prefix="/api/admin/keys", tags=["api keys"])


@router.post("", response_model=KeyCreatedOut, status_code=status.HTTP_201_CREATED)
def create_key(
    body: KeyCreate,
    user: UserOut = Depends(current_user),
    conn: dbapi.Connection = Depends(get_db),
) -> KeyCreatedOut:
    return key_service.create_key(conn, body, user)


@admin_router.delete("/{key_id}", response_model=KeyDeletedOut)
def delete_key(
    key_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> KeyDeletedOut:
    return key_service.delete_key(conn, key_id, admin)


@admin_router.post("/{key_id}/restore", response_model=KeyOut)
def restore_key(
    key_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> KeyOut:
    return key_service.restore_key(conn, key_id, admin)


@admin_router.patch("/{key_id}/servers", response_model=KeyOut)
def update_key_servers(
    body: KeyServersUpdate,
    key_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> KeyOut:
    return key_service.update_key_servers(conn, key_id, body, admin)


@admin_router.post("/{key_id}/rotate", response_model=KeyCreatedOut)
def rotate_key(
    key_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> KeyCreatedOut:
    return key_service.rotate_key(conn, key_id, admin)
