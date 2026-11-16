"""MCP servers (logged-in admin only).

POST   /api/admin/servers              register an MCP server
PATCH  /api/admin/servers/{server_id}  edit a server (only the fields sent; not if deleted)
DELETE /api/admin/servers/{server_id}  soft-delete an MCP server
POST   /api/admin/servers/{server_id}/restore
                                       undo a soft delete
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from hdbcli import dbapi

from backend.auth import current_admin
from backend.db import get_db
from backend.models import ServerCreate, ServerDeletedOut, ServerOut, ServerUpdate, UserOut
from backend.services import servers as server_service

router = APIRouter(prefix="/api/admin/servers", tags=["servers"])


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
def register_server(
    body: ServerCreate,
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerOut:
    return server_service.register_server(conn, body, admin)


@router.patch("/{server_id}", response_model=ServerOut)
def update_server(
    body: ServerUpdate,
    server_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerOut:
    return server_service.update_server(conn, server_id, body)


@router.delete("/{server_id}", response_model=ServerDeletedOut)
def delete_server(
    server_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerDeletedOut:
    return server_service.delete_server(conn, server_id, admin)


@router.post("/{server_id}/restore", response_model=ServerOut)
def restore_server(
    server_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerOut:
    return server_service.restore_server(conn, server_id)
