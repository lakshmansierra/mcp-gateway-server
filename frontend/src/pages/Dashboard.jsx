import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { formatDate, listAllServers, TRANSPORTS } from '../services/mcpService.js';

export default function Dashboard() {
  const [all, setAll] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setAll(await listAllServers());
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const live = all.filter((s) => !s.deletedAt);
  const active = live.filter((s) => s.status === 'active').length;
  const deleted = all.length - live.length;

  const byTransport = Object.keys(TRANSPORTS).map((t) => ({
    key: t,
    label: TRANSPORTS[t],
    count: live.filter((s) => s.transport === t).length,
  }));
  const maxTransport = Math.max(1, ...byTransport.map((t) => t.count));

  const recent = [...live].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 5);

  const stats = [
    { label: 'Registered Servers', value: live.length },
    { label: 'Active', value: active },
    { label: 'Inactive', value: live.length - active },
    { label: 'Deleted', value: deleted },
  ];

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-top">
          <div>
            <h1>Dashboard Overview</h1>
            <p>Monitor and manage the MCP servers connected to your gateway</p>
          </div>
          <button className="btn btn-ghost" onClick={load}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
          </button>
        </div>
        <div className="hero-stats">
          <div className="hero-summary">
            <strong>Summary</strong>
            <small>Gateway server registry</small>
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
              {recent.map((s) => (
                <li key={s.id}>
                  <span className={`dot ${s.status}`} />
                  <div className="recent-main">
                    <strong>{s.name}</strong>
                    <small className="muted">{TRANSPORTS[s.transport]} · {formatDate(s.createdAt)}</small>
                  </div>
                  <span className={`status-pill ${s.status}`}>{s.status === 'active' ? 'Active' : 'Inactive'}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
