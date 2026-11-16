"""Registering MCP servers (admin actions)."""

from __future__ import annotations

from fastapi import HTTPException, status
from hdbcli import dbapi

from backend.db import servers
from backend.models import ServerCreate, ServerDeletedOut, ServerOut, ServerUpdate, UserOut
from backend.models.server import split_tools


def to_out(row: servers.ServerRow) -> ServerOut:
    return ServerOut(
        id=row.id,
        user_id=row.user_id,
        server_name=row.server_name,
        server_url=row.server_url,
        transport=row.transport,
        timeout_seconds=row.timeout_seconds,
        enabled=bool(row.enabled),
        include_tools=split_tools(row.include_tools),
        exclude_tools=split_tools(row.exclude_tools),
        created_at=row.created_at,
    )


def register_server(conn: dbapi.Connection, body: ServerCreate, admin: UserOut) -> ServerOut:
    cur = conn.cursor()
    try:
        # server_name is UNIQUE in the table, deleted servers included. The lookup ignores case, so "ABC" and
        # "abc" can't both exist (they would be confusing as tool prefixes).
        deleted = servers.find_by_name(cur, body.server_name)
        if deleted is not None:
            detail = "belongs to a deleted server" if deleted else "already exists"
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server name '{body.server_name}' {detail}")

        row = servers.insert(
            cur,
            user_id=admin.id,
            server_name=body.server_name,
            server_url=str(body.server_url),
            transport=body.transport,
            timeout_seconds=body.timeout_seconds,
            enabled=body.enabled,
        )
        conn.commit()
    except HTTPException:
        raise
    except dbapi.IntegrityError as exc:
        # Registered by another request at the same moment: the UNIQUE constraint stopped this one.
        conn.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Server name '{body.server_name}' already exists") from exc
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return to_out(row)


def update_server(conn: dbapi.Connection, server_id: int, body: ServerUpdate) -> ServerOut:
    """Change the fields that were sent. Deleted servers can't be edited.

    Renaming a server changes its tool prefix (abc__add -> new__add); key mappings use the server id, so
    they keep working.
    """
    changes = body.changes()
    cur = conn.cursor()
    try:
        found = servers.get_by_id(cur, server_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Server {server_id} not found")
        current, is_deleted = found
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{current.server_name}' is deleted and can't be edited")

        new_name = changes.get("server_name")
        if new_name is not None:
            taken = servers.find_by_name(cur, new_name, exclude_id=server_id)
            if taken is not None:
                detail = "belongs to a deleted server" if taken else "already exists"
                raise HTTPException(status.HTTP_409_CONFLICT, f"Server name '{new_name}' {detail}")

        if not servers.update(cur, server_id, changes):  # deleted by another request in the meantime
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{current.server_name}' is deleted and can't be edited")
        row, _ = servers.get_by_id(cur, server_id)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.IntegrityError as exc:
        # Another request took the new name at the same moment: the UNIQUE constraint stopped this one.
        conn.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Server name '{changes.get('server_name')}' already exists") from exc
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return to_out(row)


def restore_server(conn: dbapi.Connection, server_id: int) -> ServerOut:
    """Undo a server's soft delete. It comes back with its old settings (including enabled/disabled),
    and keys that were mapped to it can use it again."""
    cur = conn.cursor()
    try:
        found = servers.get_by_id(cur, server_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Server {server_id} not found")
        row, is_deleted = found
        if not is_deleted or not servers.restore(cur, server_id):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{row.server_name}' is not deleted")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return to_out(row)


def delete_server(conn: dbapi.Connection, server_id: int, admin: UserOut) -> ServerDeletedOut:
    """Soft-delete a server: the row stays (is_deleted = 1, deleted_by = the admin, deleted_at = now).

    Its name stays taken. Rows in the key-to-server mapping table are kept as history; anything reading
    servers for the gateway must skip deleted ones.
    """
    cur = conn.cursor()
    try:
        found = servers.get_by_id(cur, server_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Server {server_id} not found")
        row, is_deleted = found
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{row.server_name}' is already deleted")

        deleted_at = servers.soft_delete(cur, server_id, admin.id)
        if deleted_at is None:  # deleted by another request in the meantime
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{row.server_name}' is already deleted")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return ServerDeletedOut(server=to_out(row), deleted_by=admin.id, deleted_at=deleted_at)
