import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pencil, Plus, RefreshCw, Search, Server, Trash2 } from 'lucide-react';
import AddServerModal from '../components/AddServerModal.jsx';
import { ConfirmDialog } from '../components/Modal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useToast } from '../components/Toast.jsx';
import { deleteServer, formatDate, listServers, TRANSPORTS, updateServer } from '../services/mcpService.js';

export default function McpServers() {
  const notify = useToast();
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState(null); // null | 'new' | server
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toggling, setToggling] = useState(() => new Set());

  const load = useCallback(() => {
    setLoading(true);
    setServers(listServers());
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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
      load();
    }
  };

  const toggleEnabled = async (s) => {
    const enabled = !s.enabled;
    setToggling((t) => new Set(t).add(s.id));
    setServers((list) => list.map((x) => (x.id === s.id ? { ...x, enabled } : x)));
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
      load();
    }
  };

  const activeCount = servers.filter((s) => s.enabled).length;
  const colCount = 8;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">
          <div className="icon-tile">
            <Server size={20} />
          </div>
          <div>
            <h1>MCP Servers</h1>
            <p className="muted">Servers you registered or changed from this browser</p>
          </div>
        </div>
        <button className="btn btn-outline" onClick={load}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      <div className="stat-row">
        <div className="card stat-card">
          <strong>{servers.length}</strong>
          <span>Total<br />Registered Servers</span>
        </div>
        <div className="card stat-card">
          <strong className="ok">{activeCount}</strong>
          <span>Active<br />Servers</span>
        </div>
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
                <SortHeader label="Timeout" field="timeout_seconds" sort={sort} onSort={toggle} />
                <th>Status</th>
                <SortHeader label="Created Date" field="created_at" sort={sort} onSort={toggle} />
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && servers.length === 0 ? (
                <tr><td colSpan={colCount} className="empty">Loading...</td></tr>
              ) : sorted.length === 0 ? (
                <tr><td colSpan={colCount} className="empty">{query ? 'No servers match your search' : 'No MCP servers registered from this browser yet'}</td></tr>
              ) : (
                sorted.map((s) => {
                  const status = s.enabled ? 'active' : 'inactive';
                  return (
                    <tr key={s.id}>
                      <td className="id-cell">{s.id}</td>
                      <td>
                        <div className="name-cell">
                          <strong>{s.server_name}</strong>
                          <small className="muted">Tools: {s.server_name}__*</small>
                        </div>
                      </td>
                      <td><code className="url">{s.server_url}</code></td>
                      <td><span className="tag">{TRANSPORTS[s.transport] || s.transport}</span></td>
                      <td className="nowrap">{s.timeout_seconds}s</td>
                      <td>
                        <button
                          className={`status-pill ${status}`}
                          onClick={() => toggleEnabled(s)}
                          disabled={toggling.has(s.id)}
                          title={s.enabled ? 'Click to disable' : 'Click to enable'}
                        >
                          {s.enabled ? 'Active' : 'Inactive'}
                        </button>
                      </td>
                      <td className="nowrap">{formatDate(s.created_at)}</td>
                      <td className="center nowrap">
                        <button className="icon-btn" onClick={() => setEditing(s)} title="Edit server">
                          <Pencil size={17} />
                        </button>
                        <button className="icon-btn danger-hover" onClick={() => setToDelete(s)} title="Remove server">
                          <Trash2 size={17} />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
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
            load();
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
