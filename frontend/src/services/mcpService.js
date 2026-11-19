/**
 * MCP server registry service.
 *
 * Currently backed by localStorage so the UI works standalone.
 * To connect a real backend, replace each function body with a fetch() call
 * to your gateway API. The function signatures and return shapes can stay the same.
 */

const STORAGE_KEY = 'mcp_gateway_servers';

const delay = (ms = 250) => new Promise((r) => setTimeout(r, ms));

function generateKey() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return 'mcpg_' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

const SEED = [
  { name: 'GitHub MCP', url: 'https://mcp.github.example.com/mcp', transport: 'streamable-http', authType: 'bearer', description: 'Repositories, issues and pull requests', createdAt: '2026-10-02T09:12:00Z' },
  { name: 'SAP S/4HANA Connector', url: 'https://s4-mcp.internal.example.com/mcp', transport: 'streamable-http', authType: 'api-key', description: 'Business objects and OData services', createdAt: '2026-10-18T11:40:00Z' },
  { name: 'Confluence Knowledge Base', url: 'https://wiki-mcp.example.com/sse', transport: 'sse', authType: 'bearer', description: 'Search and read wiki pages', createdAt: '2026-10-25T14:05:00Z' },
  { name: 'Postgres Analytics', url: 'https://pg-mcp.example.com/mcp', transport: 'streamable-http', authType: 'api-key', description: 'Read-only SQL over the analytics warehouse', status: 'inactive', createdAt: '2026-11-03T08:30:00Z' },
];

let memoryStore = null; // fallback when localStorage is unavailable

function read() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    // stdio is no longer supported: drop servers saved by older versions
    if (raw) return JSON.parse(raw).filter((s) => s.transport in TRANSPORTS);
  } catch {
    if (memoryStore) return memoryStore;
  }
  if (memoryStore) return memoryStore;
  const seeded = SEED.map((s, i) => ({
    id: i + 1,
    status: 'active',
    apiKey: generateKey(),
    deletedAt: null,
    ...s,
  }));
  write(seeded);
  return seeded;
}

function write(list) {
  memoryStore = list;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    /* keep in memory only */
  }
}

export async function listServers({ deleted = false } = {}) {
  await delay();
  return read().filter((s) => (deleted ? s.deletedAt : !s.deletedAt));
}

export async function listAllServers() {
  await delay();
  return read();
}

export async function addServer({ name, url, transport, authType, description, status = 'active' }) {
  await delay(400);
  const list = read();
  const trimmed = name.trim();
  if (list.some((s) => !s.deletedAt && s.name.toLowerCase() === trimmed.toLowerCase())) {
    throw new Error(`A server named "${trimmed}" already exists.`);
  }
  const server = {
    id: list.reduce((max, s) => Math.max(max, s.id), 0) + 1,
    name: trimmed,
    url: url.trim(),
    transport,
    authType,
    description: description?.trim() || '',
    status,
    apiKey: generateKey(),
    createdAt: new Date().toISOString(),
    deletedAt: null,
  };
  write([...list, server]);
  return server;
}

export async function setServerStatus(id, status) {
  await delay(150);
  write(read().map((s) => (s.id === id ? { ...s, status } : s)));
}

export async function softDeleteServer(id) {
  await delay();
  write(read().map((s) => (s.id === id ? { ...s, deletedAt: new Date().toISOString() } : s)));
}

export async function restoreServer(id) {
  await delay();
  write(read().map((s) => (s.id === id ? { ...s, deletedAt: null } : s)));
}

export async function purgeServer(id) {
  await delay();
  write(read().filter((s) => s.id !== id));
}

/* ---------- User gateway APIs ---------- */

const ACCESS_KEY = 'mcp_gateway_access';

export const GATEWAY_BASE_URL = (import.meta.env.VITE_GATEWAY_BASE_URL || 'https://mcp-gateway.example.com').replace(/\/+$/, '');

let accessMemory = null;

function readAccess() {
  try {
    const raw = localStorage.getItem(ACCESS_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* fall through to memory */
  }
  return accessMemory || [];
}

function writeAccess(list) {
  accessMemory = list;
  try {
    localStorage.setItem(ACCESS_KEY, JSON.stringify(list));
  } catch {
    /* keep in memory only */
  }
}

function generateAccessId() {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Generate one gateway API that fronts the selected MCP servers.
 * Backend equivalent: POST /api/gateway-apis { name, serverIds } -> { id, endpoint, apiKey, ... }
 */
export async function generateGatewayApi({ name, serverIds }) {
  await delay(500);
  const ids = [...new Set(serverIds)];
  if (ids.length === 0) throw new Error('Select at least one MCP server.');
  const servers = read().filter((s) => ids.includes(s.id) && !s.deletedAt);
  if (servers.length !== ids.length) throw new Error('Some selected servers are no longer available. Refresh and try again.');
  const inactive = servers.filter((s) => s.status !== 'active');
  if (inactive.length) throw new Error(`Inactive servers cannot be added: ${inactive.map((s) => s.name).join(', ')}`);

  const id = generateAccessId();
  const api = {
    id,
    name: name?.trim() || `Gateway API ${id.slice(0, 4).toUpperCase()}`,
    serverIds: servers.map((s) => s.id),
    serverNames: servers.map((s) => s.name), // snapshot, used if a server is later purged
    endpoint: `${GATEWAY_BASE_URL}/v1/gateway/${id}/mcp`,
    apiKey: generateKey(),
    createdAt: new Date().toISOString(),
  };
  writeAccess([...readAccess(), api]);
  return api;
}

export async function listGatewayApis() {
  await delay();
  return readAccess();
}

export async function revokeGatewayApi(id) {
  await delay();
  writeAccess(readAccess().filter((a) => a.id !== id));
}

/** MCP client config (Claude Desktop / Cursor style) for a generated gateway API. */
export function clientConfig(api) {
  const key = api.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'mcp-gateway';
  return JSON.stringify(
    {
      mcpServers: {
        [key]: {
          type: 'http',
          url: api.endpoint,
          headers: { Authorization: `Bearer ${api.apiKey}` },
        },
      },
    },
    null,
    2
  );
}

export const TRANSPORTS = {
  'streamable-http': 'Streamable HTTP',
  sse: 'SSE',
};

export const AUTH_TYPES = {
  none: 'None',
  'api-key': 'API Key',
  bearer: 'Bearer Token',
};

export const formatDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';
