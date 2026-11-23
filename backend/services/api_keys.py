"""Creating client-to-gateway API keys."""

from __future__ import annotations

from fastapi import HTTPException, status
from hdbcli import dbapi

from backend.db import api_keys, servers, users
from backend.models import KeyCreate, KeyCreatedOut, KeyDeletedOut, KeyOut, KeyServersUpdate, UserOut
from backend.security import new_api_key
from backend.services.ownership import require_admin_manages


def _to_out(cur: dbapi.Cursor, row: api_keys.KeyRow) -> KeyOut:
    return KeyOut(
        id=row.id,
        user_id=row.user_id,
        key_name=row.key_name,
        all_servers=bool(row.all_servers),
        server_ids=[] if row.all_servers else api_keys.mapped_server_ids(cur, row.id),
        created_at=row.created_at,
    )


def update_key_servers(conn: dbapi.Connection, key_id: int, body: KeyServersUpdate, admin: UserOut) -> KeyOut:
    """Add servers to / remove servers from a key; the key value itself doesn't change.

    Same ownership rule as deleting a key. Only keys that list their servers (all_servers = 0) can be
    changed; deleted keys can't. Added servers must be enabled, not deleted, and registered by the admin who
    created the key's user (users only reach their own admin's servers). Adding a server the key
    already has, or removing one it doesn't have, is refused so mistakes are visible. A key must keep at
    least one server.
    """
    cur = conn.cursor()
    try:
        found = api_keys.get_by_id(cur, key_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"API key {key_id} not found")
        row, is_deleted = found
        require_admin_manages(cur, row.user_id, admin, f"API key {key_id} not found")
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"API key '{row.key_name}' is deleted and can't be changed")
        if row.all_servers:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"API key '{row.key_name}' is an admin key: it already reaches every server its admin added")

        current = set(api_keys.mapped_server_ids(cur, key_id))
        already = sorted(set(body.add) & current)
        if already:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The key already has these servers: {already}")
        missing = sorted(set(body.remove) - current)
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The key doesn't have these servers: {missing}")
        key_owner = users.get_by_id(cur, row.user_id)
        users_admin = key_owner[0].created_by if key_owner else None
        unavailable = sorted(set(body.add) - servers.live_ids(cur, body.add, users_admin))
        if unavailable:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"These servers don't exist, are deleted, are disabled or weren't added by this user's admin: {unavailable}"
            )
        if not (current - set(body.remove)) | set(body.add):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A key must keep at least one server; delete the key instead")

        api_keys.unmap_servers(cur, key_id, body.remove)
        if body.add:
            api_keys.map_servers(cur, key_id, body.add)
        out = _to_out(cur, row)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return out


def delete_key(conn: dbapi.Connection, key_id: int, admin: UserOut) -> KeyDeletedOut:
    """Soft-delete a key: it stops working; the row and its mappings are kept.

    An admin may delete the keys they created and the keys of users they created.
    """
    cur = conn.cursor()
    try:
        found = api_keys.get_by_id(cur, key_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"API key {key_id} not found")
        row, is_deleted = found
        require_admin_manages(cur, row.user_id, admin, f"API key {key_id} not found")
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"API key '{row.key_name}' is already deleted")
        deleted_at = api_keys.soft_delete(cur, key_id, admin.id)
        if deleted_at is None:  # deleted by another request in the meantime
            raise HTTPException(status.HTTP_409_CONFLICT, f"API key '{row.key_name}' is already deleted")
        out = _to_out(cur, row)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return KeyDeletedOut(key=out, deleted_by=admin.id, deleted_at=deleted_at)


def restore_key(conn: dbapi.Connection, key_id: int, admin: UserOut) -> KeyOut:
    """Undo a key's soft delete; the same key value works again with its old servers. Same ownership rule as deleting.

    Refused while the key's owner is deleted: deleting a user revokes their keys on purpose, so restore the
    user first.
    """
    cur = conn.cursor()
    try:
        found = api_keys.get_by_id(cur, key_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"API key {key_id} not found")
        row, is_deleted = found
        require_admin_manages(cur, row.user_id, admin, f"API key {key_id} not found")
        if not is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"API key '{row.key_name}' is not deleted")
        owner = users.get_by_id(cur, row.user_id)
        if owner is None or owner[1]:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"The owner of API key '{row.key_name}' is deleted; restore the user first"
            )
        if not api_keys.restore(cur, key_id):
            raise HTTPException(status.HTTP_409_CONFLICT, f"API key '{row.key_name}' is not deleted")
        out = _to_out(cur, row)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return out


def rotate_key(conn: dbapi.Connection, key_id: int, admin: UserOut) -> KeyCreatedOut:
    """Give a key a new value; name and servers stay. The old value stops working at once.

    Same ownership rule as deleting a key (the admin's own keys, or keys of users they created).
    The new value is returned only here.
    """
    cur = conn.cursor()
    try:
        found = api_keys.get_by_id(cur, key_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"API key {key_id} not found")
        row, is_deleted = found
        require_admin_manages(cur, row.user_id, admin, f"API key {key_id} not found")
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"API key '{row.key_name}' is deleted; restore it first")

        key, key_hash = new_api_key()
        if not api_keys.set_hash(cur, key_id, key_hash):  # deleted by another request in the meantime
            raise HTTPException(status.HTTP_409_CONFLICT, f"API key '{row.key_name}' is deleted; restore it first")
        out = _to_out(cur, row)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return KeyCreatedOut(**out.model_dump(exclude={"user_id"}), api_key=key)


def create_key(conn: dbapi.Connection, body: KeyCreate, owner: UserOut) -> KeyCreatedOut:
    """Admins get a key for every server they added (all_servers = 1) and must not send server_ids: the mapping table
    is only for the servers users pick. Users get a key for the servers they picked (all_servers = 0, one
    mapping row each); the servers must exist, be enabled, not be deleted, and be registered by the admin who
    created the user: users can't reach another admin's servers.
    """
    is_admin = owner.type == "admin"
    if is_admin and body.server_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Admin keys reach every server you added; don't send server_ids (they are for users)"
        )
    if not is_admin and not body.server_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick at least one server in server_ids")
    server_ids = body.server_ids

    cur = conn.cursor()
    try:
        # (user_id, key_name) is UNIQUE, deleted keys included. Compared ignoring case.
        taken = api_keys.find_by_name(cur, owner.id, body.key_name)
        if taken is not None:
            detail = "belongs to one of your deleted keys" if taken else "is already used by one of your keys"
            raise HTTPException(status.HTTP_409_CONFLICT, f"Key name '{body.key_name}' {detail}")

        if server_ids:
            unavailable = sorted(set(server_ids) - servers.live_ids(cur, server_ids, owner.created_by))
            if unavailable:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"These servers don't exist, are deleted, are disabled or weren't added by your admin: {unavailable}"
                )

        key, key_hash = new_api_key()
        row = api_keys.insert(cur, user_id=owner.id, key_name=body.key_name, key_hash=key_hash, all_servers=is_admin)
        if server_ids:
            api_keys.map_servers(cur, row.id, server_ids)
        # The response shows what the mapping table now holds, not what the request asked for.
        out = _to_out(cur, row)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.IntegrityError as exc:
        # Same name created by another request at the same moment (or, practically never, a hash collision).
        conn.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Key name '{body.key_name}' is already used by one of your keys") from exc
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return KeyCreatedOut(**out.model_dump(exclude={"user_id"}), api_key=key)
