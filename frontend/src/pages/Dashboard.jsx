import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { checkHealth, formatDate, listAllServers, TRANSPORTS } from '../services/mcpService.js';

export default function Dashboard() {
  const [all, setAll] = useState([]);
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState('checking'); // 'checking' | 'ok' | 'down'

  const load = useCallback(async () => {
    setLoading(true);
    setAll(listAllServers());
    setHealth('checking');
    try {
      const h = await checkHealth();
      setHealth(h?.status === 'ok' ? 'ok' : 'down');
    } catch {
      setHealth('down');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const live = all.filter((s) => !s.deleted_at);
  const active = live.filter((s) => s.enabled).length;
  const deleted = all.length - live.length;

  const byTransport = Object.keys(TRANSPORTS).map((t) => ({
    key: t,
    label: TRANSPORTS[t],
    count: live.filter((s) => s.transport === t).length,
  }));
  const maxTransport = Math.max(1, ...byTransport.map((t) => t.count));

  const recent = [...live].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, 5);

  const stats = [
    { label: 'Registered Servers', value: live.length },
    { label: 'Active', value: active },
    { label: 'Inactive', value: live.length - active },
    { label: 'Deleted', value: deleted },
  ];

  const healthText = { checking: 'Checking backend...', ok: 'Backend & database connected', down: 'Backend unreachable' }[health];

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-top">
          <div>
            <h1>Dashboard Overview</h1>
            <p>Monitor and manage the MCP servers connected to your gateway</p>
          </div>
          <button className="btn btn-ghost" onClick={load} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
          </button>
        </div>
        <div className="hero-stats">
          <div className="hero-summary">
            <strong>Summary</strong>
            <small>{healthText}</small>
          </div>
          {stats.map((s) => (
            <div key={s.label} className="hero-stat">
              <strong>{s.value}</strong>
              <span>{s.label}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="dash-grid">
        <div className="card panel">
          <div className="panel-head">
            <h3>Servers by Transport</h3>
          </div>
          {live.length === 0 ? (
            <p className="empty">No data</p>
          ) : (
            <div className="bars">
              {byTransport.map((t) => (
                <div key={t.key} className="bar-row">
                  <span className="bar-label">{t.label}</span>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${(t.count / maxTransport) * 100}%` }} />
                  </div>
                  <span className="bar-value">{t.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card panel">
          <div className="panel-head">
            <h3>Recently Added</h3>
            <Link to="/mcp-servers" className="link">View all</Link>
          </div>
          {recent.length === 0 ? (
            <p className="empty">No data</p>
          ) : (
            <ul className="recent-list">
              {recent.map((s) => {
                const status = s.enabled ? 'active' : 'inactive';
                return (
                  <li key={s.id}>
                    <span className={`dot ${status}`} />
                    <div className="recent-main">
                      <strong>{s.server_name}</strong>
                      <small className="muted">{TRANSPORTS[s.transport] || s.transport} · {formatDate(s.created_at)}</small>
                    </div>
                    <span className={`status-pill ${status}`}>{s.enabled ? 'Active' : 'Inactive'}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
