import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, RotateCcw, Search, Trash2 } from 'lucide-react';
import { ConfirmDialog } from '../components/Modal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useToast } from '../components/Toast.jsx';
import { formatDate, listServers, restoreServer } from '../services/mcpService.js';

export default function DeletedServers() {
  const notify = useToast();
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [toRestore, setToRestore] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setServers(listServers({ deleted: true }));
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? servers.filter((s) => s.server_name.toLowerCase().includes(q)) : servers;
  }, [servers, query]);

  const { sorted, sort, toggle } = useSort(filtered, 'deleted_at', 'desc');

  const confirm = async () => {
    setBusy(true);
    try {
      const s = await restoreServer(toRestore.id);
      notify(`"${s.server_name}" restored${s.enabled ? ' and reconnected to the gateway' : ' (still disabled)'}.`);
      setToRestore(null);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
      load();
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">
          <div className="icon-tile">
            <Trash2 size={20} />
          </div>
          <div>
            <h1>Deleted Servers</h1>
            <p className="muted">Soft-deleted MCP servers. Their names stay reserved; restore them here.</p>
          </div>
        </div>
        <button className="btn btn-outline" onClick={load}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      <div className="stat-row">
        <div className="card stat-card">
          <strong>{servers.length}</strong>
          <span>Soft-deleted<br />Servers</span>
        </div>
      </div>

      <div className="card table-card">
        <div className="table-toolbar">
          <div className="search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by server name..." />
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
                <SortHeader label="Deleted At" field="deleted_at" sort={sort} onSort={toggle} />
                <SortHeader label="Created Date" field="created_at" sort={sort} onSort={toggle} />
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && servers.length === 0 ? (
                <tr><td colSpan={6} className="empty">Loading...</td></tr>
              ) : sorted.length === 0 ? (
                <tr><td colSpan={6} className="empty">{query ? 'No servers match your search' : 'No deleted servers'}</td></tr>
              ) : (
                sorted.map((s) => (
                  <tr key={s.id}>
                    <td className="id-cell">{s.id}</td>
                    <td><strong>{s.server_name}</strong></td>
                    <td><code className="url">{s.server_url}</code></td>
                    <td className="nowrap deleted-date">{formatDate(s.deleted_at)}</td>
                    <td className="nowrap">{formatDate(s.created_at)}</td>
                    <td className="center nowrap">
                      <button className="icon-btn" onClick={() => setToRestore(s)} title="Restore server">
                        <RotateCcw size={17} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {toRestore && (
        <ConfirmDialog
          title="Restore MCP server?"
          message={
            <>
              <strong>{toRestore.server_name}</strong> will be moved back to MCP Servers with its previous settings, and keys mapped to it can use it again.
            </>
          }
          confirmLabel="Restore"
          busy={busy}
          onConfirm={confirm}
          onClose={() => setToRestore(null)}
        />
      )}
    </div>
  );
}
