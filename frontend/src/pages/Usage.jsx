import { useEffect, useMemo, useState } from 'react';
import { BarChart3, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { CallStatus, CellBar, LoadError, PageHeader, StatCard, TableState } from '../components/Common.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { useLoader } from '../hooks/useLoader.js';
import {
  CALL_STATUSES,
  formatDateTime,
  formatMs,
  getCalls,
  getMyCalls,
  getMyUsage,
  getUsage,
  listMyKeys,
  listMyServers,
  listServers,
  listUsers,
  timeAgo,
} from '../services/mcpService.js';

const PAGE = 50;
const NO_FILTERS = { start: '', end: '', server_id: '', user_id: '', key_id: '', status: '' };

const pct = (n, d) => (d ? `${Math.round((n / d) * 100)}%` : '-');

/** A table of counts (per server, tool, user or key) with sortable columns. */
function CountsTable({ title, rows, nameField, nameLabel, extra, emptyText }) {
  const { sorted, sort, toggle } = useSort(rows, 'calls', 'desc');
  const max = Math.max(1, ...rows.map((r) => r.calls));
  return (
    <div className="card table-card" style={{ marginBottom: 20 }}>
      <div className="table-toolbar">
        <strong>{title}</strong>
        <span className="muted">{rows.length}</span>
      </div>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <SortHeader label={nameLabel} field={nameField} sort={sort} onSort={toggle} />
              {extra && <th>{extra.label}</th>}
              <SortHeader label="Calls" field="calls" sort={sort} onSort={toggle} />
              <SortHeader label="OK" field="ok" sort={sort} onSort={toggle} />
              <SortHeader label="Errors" field="error" sort={sort} onSort={toggle} />
              <SortHeader label="Timeouts" field="timeout" sort={sort} onSort={toggle} />
              <SortHeader label="Avg Time" field="avg_duration_ms" sort={sort} onSort={toggle} />
              <SortHeader label="Last Call" field="last_called_at" sort={sort} onSort={toggle} />
            </tr>
          </thead>
          <tbody>
            <TableState loading={false} empty={rows.length === 0} cols={extra ? 8 : 7} emptyText={emptyText} />
            {sorted.map((r) => (
              <tr key={r.key}>
                <td><strong>{r[nameField] ?? '-'}</strong></td>
                {extra && <td>{extra.render(r)}</td>}
                <td><CellBar value={r.calls} max={max} /></td>
                <td className="num">{r.ok}</td>
                <td className="num">{r.error}</td>
                <td className="num">{r.timeout}</td>
                <td className="num nowrap">{formatMs(r.avg_duration_ms)}</td>
                <td className="nowrap muted" title={formatDateTime(r.last_called_at)}>{timeAgo(r.last_called_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Admins: GET /api/admin/usage and /usage/calls (calls to tools of their servers, by anyone they manage).
 * Users: GET /api/user/usage and /usage/calls (their own calls only).
 */
export default function Usage() {
  const { isAdmin } = useAuth();
  const [tab, setTab] = useState('overview');
  const [filters, setFilters] = useState(NO_FILTERS);
  const [offset, setOffset] = useState(0);
  const [neverCalled, setNeverCalled] = useState(false);

  const fkey = JSON.stringify(filters);
  const summary = useLoader(() => (isAdmin ? getUsage(filters) : getMyUsage(filters)), [isAdmin, fkey]);
  const calls = useLoader(
    () => (tab === 'calls' ? (isAdmin ? getCalls : getMyCalls)(filters, { limit: PAGE, offset }) : Promise.resolve(null)),
    [isAdmin, fkey, offset, tab]
  );
  // Options for the filters, independent of the filters themselves.
  const servers = useLoader(() => (isAdmin ? listServers() : listMyServers()), [isAdmin], []);
  const people = useLoader(() => (isAdmin ? listUsers() : listMyKeys()), [isAdmin], []);

  useEffect(() => setOffset(0), [fkey]);

  const set = (field) => (e) => setFilters((f) => ({ ...f, [field]: e.target.value }));
  const filtered = Object.values(filters).some(Boolean);
  const s = summary.data;

  const byServer = useMemo(() => (s?.by_server || []).map((r) => ({ ...r, key: r.server_id })), [s]);
  const byTool = useMemo(
    () => (s?.by_tool || []).filter((r) => neverCalled || r.calls > 0).map((r) => ({ ...r, key: r.tool_id })),
    [s, neverCalled]
  );
  const byWho = useMemo(
    () =>
      isAdmin
        ? (s?.by_user || []).map((r) => ({ ...r, key: r.user_id, who: r.user_name ?? `#${r.user_id}` }))
        : (s?.by_key || []).map((r) => ({ ...r, key: r.key_id, who: r.key_name ?? `#${r.key_id}` })),
    [s, isAdmin]
  );

  const reloadAll = () => {
    summary.reload();
    calls.reload();
  };

  const page = calls.data;
  const total = page?.total ?? 0;

  return (
    <div className="page">
      <PageHeader
        icon={BarChart3}
        title={isAdmin ? 'Tool Usage' : 'My Usage'}
        subtitle={
          isAdmin
            ? 'Every tool call made through the gateway to your servers, by you and your users'
            : 'Every tool call you made through the gateway with your keys'
        }
        loading={summary.loading || calls.loading}
        onRefresh={reloadAll}
      >
        <div className="tabs" role="tablist">
          <button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>Overview</button>
          <button className={tab === 'calls' ? 'active' : ''} onClick={() => setTab('calls')}>Call log</button>
        </div>
      </PageHeader>

      <div className="card" style={{ padding: '14px 18px', marginBottom: 20 }}>
        <div className="filters">
          <label>From <input type="date" value={filters.start} onChange={set('start')} /></label>
          <label>To <input type="date" value={filters.end} onChange={set('end')} /></label>
          <select value={filters.server_id} onChange={set('server_id')} aria-label="Server">
            <option value="">All servers</option>
            {servers.data.map((x) => (
              <option key={x.id} value={x.id}>{x.server_name}{x.is_deleted ? ' (deleted)' : ''}</option>
            ))}
          </select>
          {isAdmin ? (
            <select value={filters.user_id} onChange={set('user_id')} aria-label="User">
              <option value="">All accounts</option>
              {people.data.map((u) => (
                <option key={u.id} value={u.id}>{u.user_name}{u.is_deleted ? ' (deleted)' : ''}</option>
              ))}
            </select>
          ) : (
            <select value={filters.key_id} onChange={set('key_id')} aria-label="Key">
              <option value="">All keys</option>
              {people.data.map((k) => (
                <option key={k.id} value={k.id}>{k.key_name}</option>
              ))}
            </select>
          )}
          <select value={filters.status} onChange={set('status')} aria-label="Status">
            <option value="">Any status</option>
            {CALL_STATUSES.map((st) => (
              <option key={st} value={st}>{st}</option>
            ))}
          </select>
          {filtered && (
            <button className="btn btn-ghost" onClick={() => setFilters(NO_FILTERS)}>
              <X size={16} /> Clear
            </button>
          )}
          <small className="muted">Dates are whole days in UTC.</small>
        </div>
      </div>

      <LoadError error={summary.error || calls.error || servers.error || people.error} onRetry={reloadAll} />

      {tab === 'overview' ? (
        <>
          <div className="stat-row">
            <StatCard value={s?.calls ?? '-'} label={<>Tool<br />Calls</>} />
            <StatCard value={s ? pct(s.ok, s.calls) : '-'} tone="ok" label={<>Succeeded<br />({s?.ok ?? 0})</>} />
            <StatCard value={s?.error ?? '-'} label={<>Errors</>} />
            <StatCard value={s?.timeout ?? '-'} label={<>Timeouts</>} />
            <StatCard value={formatMs(s?.avg_duration_ms)} label={<>Average<br />Duration</>} />
          </div>

          <CountsTable title="By server" rows={byServer} nameField="server_name" nameLabel="Server" emptyText="No servers with tools yet" />
          <CountsTable
            title={isAdmin ? 'By account' : 'By key'}
            rows={byWho}
            nameField="who"
            nameLabel={isAdmin ? 'Account' : 'Key'}
            extra={isAdmin ? { label: 'Type', render: (r) => <span className="tag">{r.type || '-'}</span> } : null}
            emptyText="No calls yet"
          />
          <div className="section-title">
            <h2>By tool</h2>
            <label className="checkbox">
              <input type="checkbox" checked={neverCalled} onChange={(e) => setNeverCalled(e.target.checked)} />
              <span>Include tools never called</span>
            </label>
          </div>
          <CountsTable
            title="Tools"
            rows={byTool.map((r) => ({ ...r, tool: r.gateway_name }))}
            nameField="tool"
            nameLabel="Tool"
            extra={isAdmin ? { label: 'State', render: (r) => (r.is_removed ? <span className="tag tag-danger">Removed</span> : <span className="tag tag-ok">Listed</span>) } : null}
            emptyText={neverCalled ? 'No tools' : 'No tool has been called yet'}
          />
        </>
      ) : (
        <div className="card table-card">
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Tool</th>
                  <th>Server</th>
                  {isAdmin && <th>Account</th>}
                  <th>Key</th>
                  <th className="num">Duration</th>
                  <th>Status</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                <TableState
                  loading={calls.loading}
                  empty={!page || page.items.length === 0}
                  cols={isAdmin ? 8 : 7}
                  emptyText={filtered ? 'No calls match your filters' : 'No calls recorded yet'}
                />
                {(page?.items || []).map((c) => (
                  <tr key={c.id}>
                    <td className="nowrap">{formatDateTime(c.called_at)}</td>
                    <td><code>{c.gateway_name}</code></td>
                    <td>{c.server_name}</td>
                    {isAdmin && <td>{c.user_name ?? `#${c.user_id}`}</td>}
                    <td>{c.key_name ?? `#${c.key_id}`}</td>
                    <td className="num nowrap">{formatMs(c.duration_ms)}</td>
                    <td><CallStatus status={c.status} /></td>
                    <td>{c.error_message ? <span className="err-text" title={c.error_message}>{c.error_message}</span> : <span className="muted">-</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span className="muted">
              {total === 0 ? 'No calls' : `${offset + 1}-${Math.min(offset + PAGE, total)} of ${total} calls`}
            </span>
            <div className="pager-buttons">
              <button className="btn btn-outline" disabled={offset === 0 || calls.loading} onClick={() => setOffset((o) => Math.max(0, o - PAGE))}>
                <ChevronLeft size={16} /> Newer
              </button>
              <button className="btn btn-outline" disabled={offset + PAGE >= total || calls.loading} onClick={() => setOffset((o) => o + PAGE)}>
                Older <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
