import { useCallback, useEffect, useMemo, useState } from 'react';
import { Eye, EyeOff, KeyRound, Plus, RefreshCw, Search, Server, Trash2, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';
import AddServerModal from '../components/AddServerModal.jsx';
import GenerateApiModal from '../components/GenerateApiModal.jsx';
import KeyCell from '../components/KeyCell.jsx';
import { ConfirmDialog } from '../components/Modal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { formatDate, listServers, setServerStatus, softDeleteServer, TRANSPORTS } from '../services/mcpService.js';

export default function McpServers() {
  const { isAdmin } = useAuth();
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [revealAll, setRevealAll] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [showGenerate, setShowGenerate] = useState(false);
  const canSelect = !isAdmin;

  const load = useCallback(async () => {
    setLoading(true);
    const list = await listServers();
    setServers(list);
    // drop selections for servers that disappeared or went inactive
    setSelected((sel) => new Set(list.filter((s) => s.status === 'active' && sel.has(s.id)).map((s) => s.id)));
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? servers.filter((s) => s.name.toLowerCase().includes(q) || s.url.toLowerCase().includes(q)) : servers;
  }, [servers, query]);

  const { sorted, sort, toggle } = useSort(filtered, 'createdAt', 'desc');

  const confirmDelete = async () => {
    setBusy(true);
    await softDeleteServer(toDelete.id);
    setBusy(false);
    setToDelete(null);
    load();
  };

  const toggleStatus = async (s) => {
    const next = s.status === 'active' ? 'inactive' : 'active';
    setServers((list) => list.map((x) => (x.id === s.id ? { ...x, status: next } : x)));
    await setServerStatus(s.id, next);
  };

  const activeCount = servers.filter((s) => s.status === 'active').length;
  const colCount = isAdmin ? 8 : 7;

  const selectable = sorted.filter((s) => s.status === 'active');
  const allVisibleSelected = selectable.length > 0 && selectable.every((s) => selected.has(s.id));
  const selectedServers = servers.filter((s) => selected.has(s.id));

  const toggleOne = (id) =>
    setSelected((sel) => {
      const next = new Set(sel);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const toggleAllVisible = () =>
    setSelected((sel) => {
      const next = new Set(sel);
      selectable.forEach((s) => (allVisibleSelected ? next.delete(s.id) : next.add(s.id)));
      return next;
    });

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">
          <div className="icon-tile">
            <Server size={20} />
          </div>
          <div>
            <h1>MCP Servers</h1>
            <p className="muted">
              {canSelect ? 'Select one or more active servers to generate a gateway API' : 'Servers registered with the gateway'}
            </p>
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
        {isAdmin && (
          <button className="add-tile" onClick={() => setShowAdd(true)} title="Add MCP server" aria-label="Add MCP server">
            <Plus size={28} />
          </button>
        )}
      </div>

      <div className="card table-card">
        <div className="table-toolbar">
          <div className="search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by server name or URL..." />
          </div>
          <span className="muted">{filtered.length} servers</span>
        </div>

        {canSelect && selected.size > 0 && (
          <div className="selection-bar">
            <span>
              <strong>{selected.size}</strong> server{selected.size === 1 ? '' : 's'} selected
            </span>
            <button className="btn-text" onClick={() => setSelected(new Set())}>
              <X size={15} /> Clear
            </button>
            <button className="btn btn-primary" onClick={() => setShowGenerate(true)}>
              <KeyRound size={16} /> Generate Gateway API
            </button>
          </div>
        )}

        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                {canSelect && (
                  <th className="check-cell">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleAllVisible}
                      disabled={selectable.length === 0}
                      aria-label="Select all active servers"
                    />
                  </th>
                )}
                <SortHeader label="ID" field="id" sort={sort} onSort={toggle} />
                <SortHeader label="Server Name" field="name" sort={sort} onSort={toggle} />
                <th>Endpoint</th>
                <th>Transport</th>
                {isAdmin && (
                  <th>
                    <div className="th-key">
                      Gateway Key
                      <button className="icon-btn subtle" onClick={() => setRevealAll((r) => !r)} title={revealAll ? 'Hide all keys' : 'Show all keys'}>
                        {revealAll ? <Eye size={17} /> : <EyeOff size={17} />}
                      </button>
                    </div>
                  </th>
                )}
                <th>Status</th>
                <SortHeader label="Created Date" field="createdAt" sort={sort} onSort={toggle} />
                {isAdmin && <th className="center">Action</th>}
              </tr>
            </thead>
            <tbody>
              {loading && servers.length === 0 ? (
                <tr><td colSpan={colCount} className="empty">Loading...</td></tr>
              ) : sorted.length === 0 ? (
                <tr><td colSpan={colCount} className="empty">{query ? 'No servers match your search' : 'No MCP servers registered yet'}</td></tr>
              ) : (
                sorted.map((s) => (
                  <tr key={s.id} className={selected.has(s.id) ? 'selected' : ''}>
                    {canSelect && (
                      <td className="check-cell">
                        <input
                          type="checkbox"
                          checked={selected.has(s.id)}
                          onChange={() => toggleOne(s.id)}
                          disabled={s.status !== 'active'}
                          title={s.status !== 'active' ? 'Inactive servers cannot be added' : undefined}
                          aria-label={`Select ${s.name}`}
                        />
                      </td>
                    )}
                    <td className="id-cell">{s.id}</td>
                    <td>
                      <div className="name-cell">
                        <strong>{s.name}</strong>
                        {s.description && <small className="muted">{s.description}</small>}
                      </div>
                    </td>
                    <td><code className="url">{s.url}</code></td>
                    <td><span className="tag">{TRANSPORTS[s.transport] || s.transport}</span></td>
                    {isAdmin && <td><KeyCell value={s.apiKey} revealedAll={revealAll} /></td>}
                    <td>
                      {isAdmin ? (
                        <button className={`status-pill ${s.status}`} onClick={() => toggleStatus(s)} title="Click to toggle">
                          {s.status === 'active' ? 'Active' : 'Inactive'}
                        </button>
                      ) : (
                        <span className={`status-pill ${s.status}`}>{s.status === 'active' ? 'Active' : 'Inactive'}</span>
                      )}
                    </td>
                    <td className="nowrap">{formatDate(s.createdAt)}</td>
                    {isAdmin && (
                      <td className="center">
                        <button className="icon-btn danger-hover" onClick={() => setToDelete(s)} title="Remove server">
                          <Trash2 size={17} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showAdd && (
        <AddServerModal
          onClose={() => setShowAdd(false)}
          onAdded={() => {
            setShowAdd(false);
            load();
          }}
        />
      )}

      {showGenerate && (
        <GenerateApiModal
          servers={selectedServers}
          onClose={() => setShowGenerate(false)}
          onGenerated={() => setSelected(new Set())}
        />
      )}

      {toDelete && (
        <ConfirmDialog
          title="Remove MCP server?"
          message={
            <>
              <strong>{toDelete.name}</strong> will be disconnected from the gateway and moved to Deleted Servers. You can restore it from there.
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
