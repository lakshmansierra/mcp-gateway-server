import { useCallback, useEffect, useMemo, useState } from 'react';
import { Eye, EyeOff, RefreshCw, RotateCcw, Search, Trash2 } from 'lucide-react';
import KeyCell from '../components/KeyCell.jsx';
import { ConfirmDialog } from '../components/Modal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { formatDate, listServers, purgeServer, restoreServer } from '../services/mcpService.js';

export default function DeletedServers() {
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [revealAll, setRevealAll] = useState(false);
  const [pending, setPending] = useState(null); // { server, action: 'restore' | 'purge' }
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setServers(await listServers({ deleted: true }));
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? servers.filter((s) => s.name.toLowerCase().includes(q)) : servers;
  }, [servers, query]);

  const { sorted, sort, toggle } = useSort(filtered, 'deletedAt', 'desc');

  const confirm = async () => {
    setBusy(true);
    if (pending.action === 'restore') await restoreServer(pending.server.id);
    else await purgeServer(pending.server.id);
    setBusy(false);
    setPending(null);
    load();
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
            <p className="muted">Soft-deleted MCP servers. Restore them or remove them permanently here.</p>
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
                <SortHeader label="Server Name" field="name" sort={sort} onSort={toggle} />
                <th>
                  <div className="th-key">
                    Gateway Key
                    <button className="icon-btn subtle" onClick={() => setRevealAll((r) => !r)} title={revealAll ? 'Hide all keys' : 'Show all keys'}>
                      {revealAll ? <Eye size={17} /> : <EyeOff size={17} />}
                    </button>
                  </div>
                </th>
                <SortHeader label="Deleted At" field="deletedAt" sort={sort} onSort={toggle} />
                <SortHeader label="Created Date" field="createdAt" sort={sort} onSort={toggle} />
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
                    <td><strong>{s.name}</strong></td>
                    <td><KeyCell value={s.apiKey} revealedAll={revealAll} /></td>
                    <td className="nowrap deleted-date">{formatDate(s.deletedAt)}</td>
                    <td className="nowrap">{formatDate(s.createdAt)}</td>
                    <td className="center nowrap">
                      <button className="icon-btn" onClick={() => setPending({ server: s, action: 'restore' })} title="Restore server">
                        <RotateCcw size={17} />
                      </button>
                      <button className="icon-btn danger-hover" onClick={() => setPending({ server: s, action: 'purge' })} title="Delete permanently">
                        <Trash2 size={17} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {pending && (
        <ConfirmDialog
          title={pending.action === 'restore' ? 'Restore MCP server?' : 'Delete permanently?'}
          message={
            pending.action === 'restore' ? (
              <>
                <strong>{pending.server.name}</strong> will be moved back to MCP Servers and reconnected to the gateway.
              </>
            ) : (
              <>
                <strong>{pending.server.name}</strong> and its gateway key will be permanently removed. This cannot be undone.
              </>
            )
          }
          confirmLabel={pending.action === 'restore' ? 'Restore' : 'Delete permanently'}
          danger={pending.action === 'purge'}
          busy={busy}
          onConfirm={confirm}
          onClose={() => setPending(null)}
        />
      )}
    </div>
  );
}
