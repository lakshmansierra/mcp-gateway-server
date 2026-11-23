import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Eye, History, Pencil, Search, Server } from 'lucide-react';
import AddServerModal from '../components/AddServerModal.jsx';
import { LoadError, PageHeader, StatCard, TableState } from '../components/Common.jsx';
import { ToolDetailsModal, ToolHistoryModal } from '../components/ToolModals.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useToast } from '../components/Toast.jsx';
import { useLoader } from '../hooks/useLoader.js';
import {
  formatDate,
  formatDateTime,
  getServer,
  getUsage,
  listServerTools,
  TRANSPORTS,
  updateServer,
} from '../services/mcpService.js';

/**
 * One server: GET /api/admin/servers/{id}, its tools (GET .../tools) with call counts (GET /api/admin/usage?server_id=),
 * and a Visible / Hidden switch per tool that edits include_tools / exclude_tools (PATCH /api/admin/servers/{id}).
 */
export default function ServerDetail() {
  const { id } = useParams();
  const notify = useToast();
  const server = useLoader(() => getServer(id), [id]);
  const tools = useLoader(() => listServerTools(id), [id], []);
  const usage = useLoader(() => getUsage({ server_id: id }), [id]);
  const [query, setQuery] = useState('');
  const [showRemoved, setShowRemoved] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [history, setHistory] = useState(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(null); // tool name being switched

  const s = server.data;
  const callsByTool = useMemo(() => new Map((usage.data?.by_tool || []).map((t) => [t.tool_id, t])), [usage.data]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tools.data
      .filter((t) => showRemoved || !t.is_removed)
      .filter((t) => !q || t.tool_name.toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q))
      .map((t) => ({ ...t, calls: callsByTool.get(t.id)?.calls || 0, last_called_at: callsByTool.get(t.id)?.last_called_at || null }));
  }, [tools.data, query, showRemoved, callsByTool]);
  const { sorted, sort, toggle } = useSort(rows, 'tool_name', 'asc');

  const reloadAll = () => {
    server.reload();
    tools.reload();
    usage.reload();
  };

  /** Show or hide one tool by changing the server's filters (only the lists that change are sent). */
  const setVisible = async (tool, visible) => {
    const include = s.include_tools;
    const exclude = s.exclude_tools;
    const changes = {};
    if (visible) {
      if (exclude.includes(tool.tool_name)) changes.exclude_tools = exclude.filter((n) => n !== tool.tool_name);
      if (!include.includes('*') && !include.includes(tool.tool_name)) changes.include_tools = [...include, tool.tool_name];
    } else {
      if (!include.includes('*') && include.includes(tool.tool_name) && include.length > 1) {
        changes.include_tools = include.filter((n) => n !== tool.tool_name);
      } else {
        changes.exclude_tools = [...exclude, tool.tool_name];
      }
    }
    setSaving(tool.tool_name);
    try {
      await updateServer(s.id, changes);
      notify(`"${tool.tool_name}" is now ${visible ? 'visible to clients' : 'hidden from clients'}.`);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setSaving(null);
      server.reload();
      tools.reload();
    }
  };

  if (server.error && !s) {
    return (
      <div className="page">
        <Link to="/mcp-servers" className="link-back"><ArrowLeft size={16} /> MCP Servers</Link>
        <LoadError error={server.error} onRetry={server.reload} />
      </div>
    );
  }

  const live = tools.data.filter((t) => !t.is_removed);
  const visible = live.filter((t) => !t.hidden).length;
  const removed = tools.data.length - live.length;
  const editable = s && !s.is_deleted;

  return (
    <div className="page">
      <Link to={s?.is_deleted ? '/deleted-servers' : '/mcp-servers'} className="link-back">
        <ArrowLeft size={16} /> {s?.is_deleted ? 'Deleted Servers' : 'MCP Servers'}
      </Link>

      <PageHeader
        icon={Server}
        title={s ? s.server_name : 'Loading...'}
        subtitle={s ? `Server #${s.id} · tools are called as ${s.server_name}__<tool>` : ''}
        loading={server.loading || tools.loading}
        onRefresh={reloadAll}
      >
        {editable && (
          <button className="btn btn-outline" onClick={() => setEditing(true)}>
            <Pencil size={16} /> Edit server
          </button>
        )}
      </PageHeader>
      <LoadError error={tools.error || usage.error} onRetry={reloadAll} />

      {s && (
        <div className="card">
          <div className="detail-grid">
            <div>
              <span>Status</span>
              <strong>
                {s.is_deleted ? (
                  <span className="status-pill deleted">Deleted</span>
                ) : (
                  <span className={`status-pill ${s.enabled ? 'active' : 'inactive'}`}>{s.enabled ? 'Active' : 'Inactive'}</span>
                )}
              </strong>
            </div>
            <div><span>Endpoint</span><code>{s.server_url}</code></div>
            <div><span>Transport</span><strong>{TRANSPORTS[s.transport] || s.transport}</strong></div>
            <div><span>Timeout</span><strong>{s.timeout_seconds}s</strong></div>
            <div><span>Include tools</span><code>{s.include_tools.join(', ')}</code></div>
            <div><span>Exclude tools</span><code>{s.exclude_tools.join(', ') || 'none'}</code></div>
            <div><span>Created</span><strong>{formatDate(s.created_at)}</strong></div>
            {s.is_deleted && <div><span>Deleted</span><strong>{formatDateTime(s.deleted_at)}</strong></div>}
          </div>
        </div>
      )}

      <div className="stat-row" style={{ marginTop: 20 }}>
        <StatCard value={live.length} label={<>Tools<br />Listed</>} />
        <StatCard value={visible} tone="ok" label={<>Visible to<br />Clients</>} />
        <StatCard value={usage.data?.calls ?? '-'} label={<>Calls<br />Recorded</>} />
        <StatCard value={removed} label={<>Removed by<br />the Server</>} />
      </div>

      <div className="card table-card">
        <div className="table-toolbar wrap">
          <div className="search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search tools..." />
          </div>
          <div className="filters">
            {removed > 0 && (
              <label className="checkbox">
                <input type="checkbox" checked={showRemoved} onChange={(e) => setShowRemoved(e.target.checked)} />
                <span>Show removed tools</span>
              </label>
            )}
            <span className="muted">{sorted.length} tools</span>
          </div>
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <SortHeader label="Tool" field="tool_name" sort={sort} onSort={toggle} />
                <th>Description</th>
                <th>Clients</th>
                <SortHeader label="Calls" field="calls" sort={sort} onSort={toggle} />
                <SortHeader label="Last Call" field="last_called_at" sort={sort} onSort={toggle} />
                <SortHeader label="First Seen" field="first_seen_at" sort={sort} onSort={toggle} />
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              <TableState
                loading={tools.loading}
                empty={sorted.length === 0}
                cols={7}
                emptyText={query ? 'No tools match your search' : 'No tools recorded yet. They appear once the gateway connects to this server.'}
              />
              {sorted.map((t) => (
                <tr key={t.id} className={t.is_removed ? 'is-dim' : ''}>
                  <td>
                    <div className="name-cell row-link" onClick={() => setViewing(t)}>
                      <strong>{t.tool_name}</strong>
                      <small className="muted">{t.gateway_name}</small>
                    </div>
                  </td>
                  <td><span className="muted" title={t.description || ''}>{(t.description || '').trim().slice(0, 90) || '-'}</span></td>
                  <td className="nowrap">
                    {t.is_removed ? (
                      <span className="tag tag-danger" title={`Removed ${formatDateTime(t.removed_at)}`}>Removed</span>
                    ) : (
                      <button
                        className={`status-pill ${t.hidden ? 'inactive' : 'active'}`}
                        onClick={() => setVisible(t, t.hidden)}
                        disabled={!editable || saving === t.tool_name}
                        title={editable ? (t.hidden ? 'Click to show to clients' : 'Click to hide from clients') : 'Restore the server to change this'}
                      >
                        {t.hidden ? 'Hidden' : 'Visible'}
                      </button>
                    )}
                  </td>
                  <td className="num">{t.calls}</td>
                  <td className="nowrap muted">{t.last_called_at ? formatDateTime(t.last_called_at) : '-'}</td>
                  <td className="nowrap">{formatDate(t.first_seen_at)}</td>
                  <td className="center nowrap">
                    <button className="icon-btn" onClick={() => setViewing(t)} title="Details and input schema">
                      <Eye size={17} />
                    </button>
                    <button className="icon-btn" onClick={() => setHistory(t)} title="History">
                      <History size={17} />
                    </button>
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
          onHistory={() => {
            setHistory(viewing);
            setViewing(null);
          }}
        />
      )}
      {history && <ToolHistoryModal tool={history} onClose={() => setHistory(null)} />}
      {editing && s && (
        <AddServerModal
          server={s}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            notify(`"${saved.server_name}" updated.`);
            setEditing(false);
            reloadAll();
          }}
        />
      )}
    </div>
  );
}
