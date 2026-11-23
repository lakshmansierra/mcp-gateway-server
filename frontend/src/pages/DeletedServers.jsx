import { useMemo, useState } from 'react';
import { RotateCcw, Search, Trash2 } from 'lucide-react';
import { LoadError, PageHeader, StatCard, TableState } from '../components/Common.jsx';
import { ConfirmDialog } from '../components/Modal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useToast } from '../components/Toast.jsx';
import { useLoader } from '../hooks/useLoader.js';
import { formatDate, formatDateTime, listServers, restoreServer } from '../services/mcpService.js';

/** The soft-deleted servers from GET /api/admin/servers (is_deleted), with POST .../restore. */
export default function DeletedServers() {
  const notify = useToast();
  const { data, error, loading, reload } = useLoader(listServers, [], []);
  const [query, setQuery] = useState('');
  const [toRestore, setToRestore] = useState(null);
  const [busy, setBusy] = useState(false);

  const servers = useMemo(() => data.filter((s) => s.is_deleted), [data]);
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
      reload();
    }
  };

  return (
    <div className="page">
      <PageHeader
        icon={Trash2}
        title="Deleted Servers"
        subtitle="Soft-deleted MCP servers. Their names stay reserved; restore them here."
        loading={loading}
        onRefresh={reload}
      />
      <LoadError error={error} onRetry={reload} />

      <div className="stat-row">
        <StatCard value={servers.length} label={<>Soft-deleted<br />Servers</>} />
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
                <SortHeader label="Tools" field="tool_count" sort={sort} onSort={toggle} />
                <SortHeader label="Deleted At" field="deleted_at" sort={sort} onSort={toggle} />
                <SortHeader label="Created Date" field="created_at" sort={sort} onSort={toggle} />
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              <TableState loading={loading} empty={sorted.length === 0} cols={7} emptyText={query ? 'No servers match your search' : 'No deleted servers'} />
              {sorted.map((s) => (
                <tr key={s.id}>
                  <td className="id-cell">{s.id}</td>
                  <td><strong>{s.server_name}</strong></td>
                  <td><code className="url">{s.server_url}</code></td>
                  <td className="nowrap">{s.tool_count}</td>
                  <td className="nowrap deleted-date" title={formatDateTime(s.deleted_at)}>{formatDate(s.deleted_at)}</td>
                  <td className="nowrap">{formatDate(s.created_at)}</td>
                  <td className="center nowrap">
                    <button className="icon-btn" onClick={() => setToRestore(s)} title="Restore server">
                      <RotateCcw size={17} />
                    </button>
                  </td>
                </tr>
              ))}
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
