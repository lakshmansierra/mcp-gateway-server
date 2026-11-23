import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Pencil, Plus, Search, Server, Trash2, Wrench } from 'lucide-react';
import AddServerModal from '../components/AddServerModal.jsx';
import { LoadError, PageHeader, StatCard, TableState } from '../components/Common.jsx';
import { ConfirmDialog } from '../components/Modal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useToast } from '../components/Toast.jsx';
import { useLoader } from '../hooks/useLoader.js';
import { deleteServer, formatDate, listServers, TRANSPORTS, updateServer } from '../services/mcpService.js';

/** GET /api/admin/servers (live ones; deleted ones are on Deleted Servers) with edit, enable/disable and delete. */
export default function McpServers() {
  const notify = useToast();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useLoader(listServers, [], []);
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState(null); // null | 'new' | server
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toggling, setToggling] = useState(() => new Set());

  const servers = useMemo(() => data.filter((s) => !s.is_deleted), [data]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? servers.filter((s) => s.server_name.toLowerCase().includes(q) || s.server_url.toLowerCase().includes(q)) : servers;
  }, [servers, query]);
  const { sorted, sort, toggle } = useSort(filtered, 'created_at', 'desc');

  const confirmDelete = async () => {
    setBusy(true);
    try {
      await deleteServer(toDelete.id);
      notify(`"${toDelete.server_name}" moved to Deleted Servers.`);
      setToDelete(null);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
      reload();
    }
  };

  const toggleEnabled = async (s) => {
    const enabled = !s.enabled;
    setToggling((t) => new Set(t).add(s.id));
    try {
      await updateServer(s.id, { enabled });
      notify(`"${s.server_name}" ${enabled ? 'enabled' : 'disabled'}.`);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setToggling((t) => {
        const next = new Set(t);
        next.delete(s.id);
        return next;
      });
      reload();
    }
  };

  const activeCount = servers.filter((s) => s.enabled).length;
  const toolCount = servers.reduce((n, s) => n + s.tool_count, 0);
  const cols = 9;

  return (
    <div className="page">
      <PageHeader icon={Server} title="MCP Servers" subtitle="Servers you registered with the gateway" loading={loading} onRefresh={reload} />
      <LoadError error={error} onRetry={reload} />

      <div className="stat-row">
        <StatCard value={servers.length} label={<>Registered<br />Servers</>} />
        <StatCard value={activeCount} tone="ok" label={<>Active<br />Servers</>} />
        <StatCard value={toolCount} label={<>Tools<br />Listed</>} />
        <button className="add-tile" onClick={() => setEditing('new')} title="Add MCP server" aria-label="Add MCP server">
          <Plus size={28} />
        </button>
      </div>

      <div className="card table-card">
        <div className="table-toolbar">
          <div className="search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by server name or URL..." />
          </div>
          <span className="muted">{filtered.length} servers</span>
        </div>

        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <SortHeader label="ID" field="id" sort={sort} onSort={toggle} />
                <SortHeader label="Server Name" field="server_name" sort={sort} onSort={toggle} />
                <th>Endpoint</th>
                <th>Transport</th>
                <SortHeader label="Tools" field="tool_count" sort={sort} onSort={toggle} />
                <SortHeader label="Timeout" field="timeout_seconds" sort={sort} onSort={toggle} />
                <th>Status</th>
                <SortHeader label="Created Date" field="created_at" sort={sort} onSort={toggle} />
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              <TableState
                loading={loading}
                empty={sorted.length === 0}
                cols={cols}
                emptyText={query ? 'No servers match your search' : 'No MCP servers registered yet'}
              />
              {sorted.map((s) => (
                <tr key={s.id}>
                  <td className="id-cell">{s.id}</td>
                  <td>
                    <div className="name-cell row-link" onClick={() => navigate(`/mcp-servers/${s.id}`)}>
                      <strong>{s.server_name}</strong>
                      <small className="muted">Tools: {s.server_name}__*</small>
                    </div>
                  </td>
                  <td><code className="url">{s.server_url}</code></td>
                  <td><span className="tag">{TRANSPORTS[s.transport] || s.transport}</span></td>
                  <td className="nowrap">
                    <button className="btn-text" onClick={() => navigate(`/mcp-servers/${s.id}`)} title="View tools">
                      {s.tool_count}
                    </button>
                  </td>
                  <td className="nowrap">{s.timeout_seconds}s</td>
                  <td>
                    <button
                      className={`status-pill ${s.enabled ? 'active' : 'inactive'}`}
                      onClick={() => toggleEnabled(s)}
                      disabled={toggling.has(s.id)}
                      title={s.enabled ? 'Click to disable' : 'Click to enable'}
                    >
                      {s.enabled ? 'Active' : 'Inactive'}
                    </button>
                  </td>
                  <td className="nowrap">{formatDate(s.created_at)}</td>
                  <td className="center nowrap">
                    <button className="icon-btn" onClick={() => navigate(`/mcp-servers/${s.id}`)} title="Tools and details">
                      <Wrench size={17} />
                    </button>
                    <button className="icon-btn" onClick={() => setEditing(s)} title="Edit server">
                      <Pencil size={17} />
                    </button>
                    <button className="icon-btn danger-hover" onClick={() => setToDelete(s)} title="Remove server">
                      <Trash2 size={17} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {editing && (
        <AddServerModal
          server={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(s) => {
            notify(editing === 'new' ? `"${s.server_name}" registered with the gateway.` : `"${s.server_name}" updated.`);
            setEditing(null);
            reload();
          }}
        />
      )}

      {toDelete && (
        <ConfirmDialog
          title="Remove MCP server?"
          message={
            <>
              <strong>{toDelete.server_name}</strong> will be disconnected from the gateway and moved to Deleted Servers. You can restore it from there.
            </>
          }
          confirmLabel="Remove"
          danger
          busy={busy}
          onConfirm={confirmDelete}
          onClose={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
