/**
 * MCP Gateway backend API: one function per endpoint in the backend's OpenAPI (Swagger) docs.
 *
 * Request bodies match the backend schemas exactly (LoginRequest, ServerCreate, ServerUpdate, KeyCreate,
 * KeyServersUpdate, RegisterRequest, PasswordChange, PasswordReset). Every successful response is also
 * written to the local registry (see registry.js), because the backend offers no list endpoints.
 *
 * POST /api/admin/register is intentionally not wrapped here.
 */

import { ApiError, currentSession, request } from './api.js';
import * as registry from './registry.js';

/* ---------- Constants ---------- */

/** ServerCreate.transport enum */
export const TRANSPORTS = {
  streamable_http: 'Streamable HTTP',
  sse: 'SSE',
};

/** Shared pattern of RegisterRequest.user_name and KeyCreate.key_name */
export const NAME_PATTERN = /^[A-Za-z0-9._-]+$/;
/** ServerCreate.server_name */
export const SERVER_NAME_PATTERN = /^[A-Za-z0-9_-]+$/;
export const MIN_PASSWORD = 8;

/** The gateway's single MCP endpoint; API keys decide which servers a client reaches. */
export const GATEWAY_MCP_URL = (import.meta.env.VITE_GATEWAY_MCP_URL || '').replace(/\/+$/, '');

const me = () => currentSession()?.user || null;

/** Drop a stale local record when the backend says it no longer exists. */
async function withNotFound(collection, id, fn) {
  try {
    return await fn();
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) registry.remove(collection, id);
    throw err;
  }
}

/* ---------- Health ---------- */

/** GET /api/health -> { status, database } */
export const checkHealth = () => request('GET', '/api/health', { auth: false });

/* ---------- Accounts ---------- */

/**
 * POST /api/admin/login or POST /api/user/login with LoginRequest { user_name, password }
 * @returns TokenOut { access_token, token_type, expires_in, user }
 */
export function login(kind, user_name, password) {
  const path = kind === 'admin' ? '/api/admin/login' : '/api/user/login';
  return request('POST', path, { body: { user_name, password }, auth: false });
}

/** POST /api/me/logout: ends this device's session only. */
export const logout = () => request('POST', '/api/me/logout');

/** POST /api/me/logout-all: ends the session on every device. */
export const logoutAll = () => request('POST', '/api/me/logout-all');

/** PATCH /api/me/password with PasswordChange { old_password, new_password }; logs out everywhere. */
export const changePassword = (old_password, new_password) =>
  request('PATCH', '/api/me/password', { body: { old_password, new_password } });

/* ---------- MCP servers (admin) ---------- */

export function listServers({ deleted = false } = {}) {
  return registry.list('servers').filter((s) => (deleted ? s.deleted_at : !s.deleted_at));
}

export const listAllServers = () => registry.list('servers');

/**
 * POST /api/admin/servers with ServerCreate { server_name, server_url, transport, timeout_seconds, enabled }
 * @returns ServerOut
 */
export async function registerServer({ server_name, server_url, transport, timeout_seconds, enabled }) {
  const out = await request('POST', '/api/admin/servers', {
    body: { server_name, server_url, transport, timeout_seconds, enabled },
  });
  return registry.upsert('servers', { ...out, deleted_at: null });
}

/**
 * PATCH /api/admin/servers/{id} with ServerUpdate: only the fields to change.
 * @returns ServerOut
 */
export function updateServer(id, changes) {
  return withNotFound('servers', id, async () => {
    const out = await request('PATCH', `/api/admin/servers/${id}`, { body: changes });
    return registry.upsert('servers', { ...out, deleted_at: null });
  });
}

/** DELETE /api/admin/servers/{id} (soft delete) -> ServerDeletedOut { server, deleted_by, deleted_at } */
export function deleteServer(id) {
  return withNotFound('servers', id, async () => {
    const out = await request('DELETE', `/api/admin/servers/${id}`);
    return registry.upsert('servers', { ...out.server, deleted_at: out.deleted_at, deleted_by: out.deleted_by });
  });
}

/** POST /api/admin/servers/{id}/restore -> ServerOut */
export function restoreServer(id) {
  return withNotFound('servers', id, async () => {
    const out = await request('POST', `/api/admin/servers/${id}/restore`);
    return registry.upsert('servers', { ...out, deleted_at: null, deleted_by: null });
  });
}

/* ---------- Gateway API keys ---------- */

export const listKeys = () => registry.list('keys');

/**
 * POST /api/keys with KeyCreate { key_name, server_ids? }.
 * Admins must leave server_ids out (their keys reach every server they added); users must send at least one.
 * @returns KeyCreatedOut, including the plain api_key (returned only this once; not stored)
 */
export async function createKey({ key_name, server_ids }) {
  const body = server_ids?.length ? { key_name, server_ids } : { key_name };
  const out = await request('POST', '/api/keys', { body });
  const { api_key, ...rest } = out;
  registry.upsert('keys', { ...rest, user_id: me()?.id, deleted_at: null });
  return out;
}

/** DELETE /api/admin/keys/{id} (admin; soft delete) -> KeyDeletedOut { key, deleted_by, deleted_at } */
export function deleteKey(id) {
  return withNotFound('keys', id, async () => {
    const out = await request('DELETE', `/api/admin/keys/${id}`);
    return registry.upsert('keys', { ...out.key, deleted_at: out.deleted_at, deleted_by: out.deleted_by });
  });
}

/** POST /api/admin/keys/{id}/restore (admin) -> KeyOut */
export function restoreKey(id) {
  return withNotFound('keys', id, async () => {
    const out = await request('POST', `/api/admin/keys/${id}/restore`);
    return registry.upsert('keys', { ...out, deleted_at: null, deleted_by: null });
  });
}

/** PATCH /api/admin/keys/{id}/servers (admin) with KeyServersUpdate { add, remove } -> KeyOut */
export function updateKeyServers(id, { add = [], remove = [] }) {
  return withNotFound('keys', id, async () => {
    const out = await request('PATCH', `/api/admin/keys/${id}/servers`, { body: { add, remove } });
    return registry.upsert('keys', { ...out, deleted_at: null });
  });
}

/** POST /api/admin/keys/{id}/rotate (admin) -> KeyCreatedOut with the new plain api_key (not stored) */
export function rotateKey(id) {
  return withNotFound('keys', id, async () => {
    const out = await request('POST', `/api/admin/keys/${id}/rotate`);
    const { api_key, ...rest } = out;
    registry.upsert('keys', { ...rest, deleted_at: null });
    return out;
  });
}

/* ---------- Users (admin) ---------- */

export const listUsers = () => registry.list('users');

/** POST /api/admin/users with RegisterRequest { user_name, password } -> UserOut */
export async function createUser({ user_name, password }) {
  const out = await request('POST', '/api/admin/users', { body: { user_name, password } });
  return registry.upsert('users', { ...out, deleted_at: null });
}

/**
 * DELETE /api/admin/users/{id} -> UserDeletedOut { user, deleted_by, deleted_at, api_keys_revoked }.
 * The backend revokes the user's keys, so the tracked ones are marked revoked too.
 */
export function deleteUser(id) {
  return withNotFound('users', id, async () => {
    const out = await request('DELETE', `/api/admin/users/${id}`);
    registry.updateWhere(
      'keys',
      (k) => k.user_id === id && !k.deleted_at,
      (k) => ({ ...k, deleted_at: out.deleted_at, deleted_by: out.deleted_by })
    );
    registry.upsert('users', { ...out.user, deleted_at: out.deleted_at, deleted_by: out.deleted_by });
    return out;
  });
}

/** POST /api/admin/users/{id}/restore -> UserOut (their keys stay revoked) */
export function restoreUser(id) {
  return withNotFound('users', id, async () => {
    const out = await request('POST', `/api/admin/users/${id}/restore`);
    return registry.upsert('users', { ...out, deleted_at: null, deleted_by: null });
  });
}

/** PATCH /api/admin/users/{id}/password with PasswordReset { new_password } -> UserOut */
export function resetUserPassword(id, new_password) {
  return withNotFound('users', id, async () => {
    const out = await request('PATCH', `/api/admin/users/${id}/password`, { body: { new_password } });
    return registry.upsert('users', out);
  });
}

/* ---------- Helpers ---------- */

/** "3, 7 12" -> [3, 7, 12]; throws on anything that isn't a positive whole number. */
export function parseIds(text) {
  const parts = String(text || '')
    .split(/[\s,]+/)
    .filter(Boolean);
  const ids = parts.map((p) => Number(p));
  const bad = parts.filter((p, i) => !Number.isInteger(ids[i]) || ids[i] <= 0);
  if (bad.length) throw new Error(`Not a valid server ID: ${bad.join(', ')}`);
  return [...new Set(ids)];
}

/** "add, server_1__sub\nmul" -> ['add', 'server_1__sub', 'mul'] */
export const parseNames = (text) =>
  String(text || '')
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

/** MCP client config (Claude Desktop / Cursor / VS Code style) for a gateway API key. */
export function clientConfig(name, apiKey) {
  const key = String(name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'mcp-gateway';
  return JSON.stringify(
    {
      mcpServers: {
        [key]: {
          type: 'http',
          url: GATEWAY_MCP_URL || '<gateway MCP URL>',
          headers: { Authorization: `Bearer ${apiKey || '<your API key>'}` },
        },
      },
    },
    null,
    2
  );
}

export const formatDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';
