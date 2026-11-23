import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, History, Search, Server, Wrench } from 'lucide-react';
import { LoadError, PageHeader, StatCard, TableState } from '../components/Common.jsx';
import { ToolDetailsModal, ToolHistoryModal } from '../components/ToolModals.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { useLoader } from '../hooks/useLoader.js';
import {
  formatDate,
  formatDateTime,
  getMyUsage,
  getUsage,
  listMyServers,
  listMyTools,
  listTools,
} from '../services/mcpService.js';

/**
 * Admins: every tool of their servers (GET /api/admin/tools), tagged hidden / removed / server deleted, with history.
 * Users: the servers they may use (GET /api/user/servers) and the tools they can call (GET /api/user/tools).
 * Call counts come from the usage summary of each role.
 */
export default function Tools() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const tools = useLoader(() => (isAdmin ? listTools() : listMyTools()), [isAdmin], []);
  const usage = useLoader(() => (isAdmin ? getUsage() : getMyUsage()), [isAdmin]);
  const myServers = useLoader(() => (isAdmin ? Promise.resolve([]) : listMyServers()), [isAdmin], []);
  const [query, setQuery] = useState('');
  const [serverId, setServerId] = useState('');
  const [state, setState] = useState(isAdmin ? 'current' : 'all');
  const [viewing, setViewing] = useState(null);
  const [history, setHistory] = useState(null);

  const calls = useMemo(() => new Map((usage.data?.by_tool || []).map((t) => [t.tool_id, t.calls])), [usage.data]);

  // The server filter: the user's servers, or (admin) every server that has tools.
  const serverOptions = useMemo(() => {
    if (!isAdmin) return myServers.data.map((s) => ({ id: s.id, name: s.server_name }));
    const seen = new Map();
    for (const t of tools.data) seen.set(t.server_id, { id: t.server_id, name: t.server_name + (t.server_is_deleted ? ' (deleted)' : '') });
    return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [isAdmin, tools.data, myServers.data]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tools.data
      .filter((t) => !serverId || String(t.server_id) === serverId)
      .filter((t) => {
        if (!isAdmin || state === 'all') return true;
        const current = !t.is_removed && !t.server_is_deleted;
        if (state === 'current') return current;
        if (state === 'visible') return current && !t.hidden && t.server_enabled;
        if (state === 'hidden') return current && t.hidden;
        return t.is_removed || t.server_is_deleted; // 'gone'
      })
      .filter((t) => !q || t.tool_name.toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q))
      .map((t) => ({ ...t, calls: calls.get(t.id) || 0 }));
  }, [tools.data, serverId, state, query, isAdmin, calls]);
  const { sorted, sort, toggle } = useSort(rows, 'server_name', 'asc');

  const reloadAll = () => {
    tools.reload();
    usage.reload();
    myServers.reload();
  };

  const current = tools.data.filter((t) => !t.is_removed && !t.server_is_deleted);
  const cols = isAdmin ? 7 : 6;

  const statusTags = (t) => {
    if (!isAdmin) return <span className="tag tag-ok">Available</span>;
    if (t.server_is_deleted) return <span className="tag tag-danger">Server deleted</span>;
    if (t.is_removed) return <span className="tag tag-danger" title={`Removed ${formatDateTime(t.removed_at)}`}>Removed</span>;
    return (
      <div className="tag-list">
        <span className={`tag ${t.hidden ? 'tag-muted' : 'tag-ok'}`}>{t.hidden ? 'Hidden' : 'Visible'}</span>
        {!t.server_enabled && <span className="tag tag-warn">Server disabled</span>}
      </div>
    );
  };

  return (
    <div className="page">
      <PageHeader
        icon={Wrench}
        title={isAdmin ? 'Tools' : 'Servers & Tools'}
        subtitle={
          isAdmin
            ? 'Every tool your servers list, as the gateway last saw it. Hide or show tools on a server’s page.'
            : 'The servers your admin gave you and the tools you can call through the gateway'
        }
        loading={tools.loading}
        onRefresh={reloadAll}
      />
      <LoadError error={tools.error || usage.error || myServers.error} onRetry={reloadAll} />

      {isAdmin ? (
        <div className="stat-row">
          <StatCard value={current.length} label={<>Tools<br />Listed</>} />
          <StatCard value={current.filter((t) => !t.hidden).length} tone="ok" label={<>Visible to<br />Clients</>} />
          <StatCard value={current.filter((t) => t.hidden).length} label={<>Hidden by<br />Filters</>} />
          <StatCard value={usage.data?.calls ?? '-'} label={<>Calls<br />Recorded</>} />
        </div>
      ) : (
        <>
          <div className="stat-row">
            <StatCard value={myServers.data.length} label={<>Servers<br />Available</>} />
            <StatCard value={tools.data.length} tone="ok" label={<>Tools You<br />Can Call</>} />
            <StatCard value={usage.data?.calls ?? '-'} label={<>Your<br />Calls</>} />
          </div>
          <div className="card table-card" style={{ marginBottom: 20 }}>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Server</th>
                    <th>Tools</th>
                    <th>Added</th>
                  </tr>
                </thead>
                <tbody>
                  <TableState loading={myServers.loading} empty={myServers.data.length === 0} cols={4} emptyText="Your admin hasn't added any servers yet" />
                  {myServers.data.map((s) => (
                    <tr key={s.id} className="row-link" onClick={() => setServerId(String(s.id))}>
                      <td className="id-cell">{s.id}</td>
                      <td>
                        <div className="name-cell">
                          <strong><Server size={14} /> {s.server_name}</strong>
                          <small className="muted">Tools: {s.server_name}__*</small>
                        </div>
                      </td>
                      <td>{s.tool_count}</td>
                      <td className="nowrap">{formatDate(s.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      <div className="card table-card">
        <div className="table-toolbar wrap">
          <div className="search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search tools..." />
          </div>
          <div className="filters">
            <select value={serverId} onChange={(e) => setServerId(e.target.value)} aria-label="Server">
              <option value="">All servers</option>
              {serverOptions.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
            {isAdmin && (
              <select value={state} onChange={(e) => setState(e.target.value)} aria-label="Tool state">
                <option value="current">Listed now</option>
                <option value="visible">Visible to clients</option>
                <option value="hidden">Hidden by filters</option>
                <option value="gone">Removed / server deleted</option>
                <option value="all">All, ever</option>
              </select>
            )}
            <span className="muted">{sorted.length} tools</span>
          </div>
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <SortHeader label="Tool" field="tool_name" sort={sort} onSort={toggle} />
                <SortHeader label="Server" field="server_name" sort={sort} onSort={toggle} />
                <th>Description</th>
                <th>Status</th>
                <SortHeader label="Calls" field="calls" sort={sort} onSort={toggle} />
                {isAdmin && <SortHeader label="First Seen" field="first_seen_at" sort={sort} onSort={toggle} />}
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              <TableState
                loading={tools.loading}
                empty={sorted.length === 0}
                cols={cols}
                emptyText={query || serverId ? 'No tools match your filters' : 'No tools yet. They appear once the gateway connects to a server.'}
              />
              {sorted.map((t) => (
                <tr key={t.id} className={t.is_removed || t.server_is_deleted ? 'is-dim' : ''}>
                  <td>
                    <div className="name-cell row-link" onClick={() => setViewing(t)}>
                      <strong>{t.tool_name}</strong>
                      <small className="muted">{t.gateway_name}</small>
                    </div>
                  </td>
                  <td>
                    {isAdmin ? (
                      <button className="btn-text" onClick={() => navigate(`/mcp-servers/${t.server_id}`)}>{t.server_name}</button>
                    ) : (
                      t.server_name
                    )}
                  </td>
                  <td><span className="muted" title={t.description || ''}>{(t.description || '').trim().slice(0, 80) || '-'}</span></td>
                  <td className="nowrap">{statusTags(t)}</td>
                  <td className="num">{t.calls}</td>
                  {isAdmin && <td className="nowrap">{formatDate(t.first_seen_at)}</td>}
                  <td className="center nowrap">
                    <button className="icon-btn" onClick={() => setViewing(t)} title="Details and input schema">
                      <Eye size={17} />
                    </button>
                    {isAdmin && (
                      <button className="icon-btn" onClick={() => setHistory(t)} title="History">
                        <History size={17} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {viewing && (
        <ToolDetailsModal
          tool={viewing}
          onClose={() => setViewing(null)}
          onHistory={
            isAdmin
              ? () => {
                  setHistory(viewing);
                  setViewing(null);
                }
              : undefined
          }
        />
      )}
      {history && <ToolHistoryModal tool={history} onClose={() => setHistory(null)} />}
    </div>
  );
}
