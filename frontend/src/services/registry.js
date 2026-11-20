/**
 * Local record of the servers, API keys and users this account has created or changed.
 *
 * The backend has no list (GET) endpoints for servers, keys or users, so the tables in the UI are built
 * from the objects the backend returned on create / update / delete / restore. Each record is stored
 * exactly as the API returned it, plus `deleted_at` (null while live). Records are kept per account
 * (by user id) in localStorage. Plain API keys are never stored: the backend returns them only once.
 */

import { currentSession } from './api.js';

const PREFIX = 'mcp_gateway_registry_v1';
const memory = {}; // fallback when localStorage is unavailable

// The old UI kept demo servers and fake gateway APIs here; they have nothing to do with the backend.
try {
  localStorage.removeItem('mcp_gateway_servers');
  localStorage.removeItem('mcp_gateway_access');
} catch {
  /* storage unavailable */
}

function storageKey() {
  const id = currentSession()?.user?.id;
  return id == null ? null : `${PREFIX}:${id}`;
}

function load() {
  const key = storageKey();
  if (!key) return { servers: {}, keys: {}, users: {} };
  try {
    const raw = localStorage.getItem(key);
    if (raw) return { servers: {}, keys: {}, users: {}, ...JSON.parse(raw) };
  } catch {
    /* fall through to memory */
  }
  return memory[key] || { servers: {}, keys: {}, users: {} };
}

function save(data) {
  const key = storageKey();
  if (!key) return;
  memory[key] = data;
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    /* keep in memory only */
  }
}

/** @param {'servers'|'keys'|'users'} collection */
export function list(collection) {
  return Object.values(load()[collection]);
}

export function get(collection, id) {
  return load()[collection][id] || null;
}

/** Merge `record` into the stored one with the same id (fields not sent are kept). */
export function upsert(collection, record) {
  const data = load();
  const prev = data[collection][record.id] || {};
  const next = { ...prev, ...record };
  data[collection][record.id] = next;
  save(data);
  return next;
}

export function remove(collection, id) {
  const data = load();
  delete data[collection][id];
  save(data);
}

/** Apply `fn` to every record in a collection that matches `where`. */
export function updateWhere(collection, where, fn) {
  const data = load();
  for (const [id, rec] of Object.entries(data[collection])) {
    if (where(rec)) data[collection][id] = fn(rec);
  }
  save(data);
}
