import { RefreshCw } from 'lucide-react';

/** Title row of a page: icon tile, heading, subtitle, then actions (always a Refresh button when onRefresh is given). */
export function PageHeader({ icon: Icon, title, subtitle, loading, onRefresh, children }) {
  return (
    <div className="page-header">
      <div className="page-title">
        <div className="icon-tile">
          <Icon size={20} />
        </div>
        <div>
          <h1>{title}</h1>
          {subtitle && <p className="muted">{subtitle}</p>}
        </div>
      </div>
      <div className="header-actions">
        {children}
        {onRefresh && (
          <button className="btn btn-outline" onClick={onRefresh} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
          </button>
        )}
      </div>
    </div>
  );
}

export function StatCard({ value, label, tone }) {
  return (
    <div className="card stat-card">
      <strong className={tone || ''}>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

/** A load error, with a retry button. */
export function LoadError({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="alert-error" style={{ marginBottom: 16 }}>
      {error}{' '}
      {onRetry && (
        <button className="btn-text" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

const CALL_PILL = { ok: 'active', error: 'deleted', timeout: 'inactive' };

/** ok / error / timeout of a tools/call */
export function CallStatus({ status }) {
  return <span className={`status-pill ${CALL_PILL[status] || 'inactive'}`}>{status}</span>;
}

/** Table body placeholder rows: loading, empty, or nothing (when there are rows). */
export function TableState({ loading, empty, cols, emptyText }) {
  if (loading && empty) {
    return (
      <tr>
        <td colSpan={cols} className="empty">Loading...</td>
      </tr>
    );
  }
  if (empty) {
    return (
      <tr>
        <td colSpan={cols} className="empty">{emptyText}</td>
      </tr>
    );
  }
  return null;
}

/** A horizontal bar for a value out of `max`, with the number next to it. */
export function CellBar({ value, max, label }) {
  const pct = max ? Math.round((value / max) * 100) : 0;
  return (
    <div className="cell-bar">
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="num">{label ?? value}</span>
    </div>
  );
}
