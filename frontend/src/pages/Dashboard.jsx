import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Bot,
  KeyRound,
  Laptop,
  Plus,
  RefreshCw,
  Server,
  Terminal,
  Trash2,
  UserPlus,
  Users,
} from 'lucide-react';
import { LogoMark } from '../components/Logo.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { formatDate, listAllServers, listKeys, listUsers, TRANSPORTS } from '../services/mcpService.js';

const TOPOLOGY_LIMIT = 5;

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

function KpiCard({ icon: Icon, label, value, detail, percent, tone = 'blue' }) {
  return (
    <div className={`card kpi ${tone}`}>
      <div className="kpi-top">
        <span className="kpi-icon">
          <Icon size={20} strokeWidth={1.8} />
        </span>
        <span className="kpi-label">{label}</span>
      </div>
      <strong className="kpi-value">{value}</strong>
      <div className="kpi-meter">
        <span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
      </div>
      <small className="kpi-detail">{detail}</small>
    </div>
  );
}

export default function Dashboard() {
  const { username } = useAuth();
  const { health, refreshHealth } = useOutletContext();
  const [servers, setServers] = useState([]);
  const [keys, setKeys] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setServers(listAllServers());
    setKeys(listKeys());
    setUsers(listUsers());
    await refreshHealth();
    setLoading(false);
  }, [refreshHealth]);

  useEffect(() => {
    load();
  }, [load]);

  const live = servers.filter((s) => !s.deleted_at);
  const active = live.filter((s) => s.enabled).length;
  const deleted = servers.length - live.length;
  const liveKeys = keys.filter((k) => !k.deleted_at).length;
  const liveUsers = users.filter((u) => !u.deleted_at).length;
  const pct = (n, d) => (d ? Math.round((n / d) * 100) : 0);

  const byTransport = Object.keys(TRANSPORTS).map((t) => ({
    key: t,
    label: TRANSPORTS[t],
    count: live.filter((s) => s.transport === t).length,
  }));

  const recent = [...live].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  const topology = recent.slice(0, TOPOLOGY_LIMIT);

  const healthLabel = { checking: 'Checking status...', ok: 'All systems operational', down: 'Backend unreachable' }[health];

  const actions = [
    { to: '/mcp-servers', icon: Server, title: 'Register MCP server', text: 'Connect a new upstream server to the gateway' },
    { to: '/gateway-apis', icon: KeyRound, title: 'Generate API key', text: 'Give an MCP client access through the gateway' },
    { to: '/users', icon: UserPlus, title: 'Create user', text: 'Add an account that can request its own keys' },
    { to: '/deleted-servers', icon: Trash2, title: 'Review deleted servers', text: 'Restore servers removed from the gateway' },
  ];

  return (
    <div className="page">
      <section className="welcome">
        <div>
          <p className="eyebrow">{new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
          <h1>
            {greeting()}, {username}
          </h1>
          <p className="muted">Here is the state of your MCP gateway.</p>
        </div>
        <div className="header-actions">
          <button className="btn btn-outline" onClick={load} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
          </button>
          <Link to="/mcp-servers" className="btn btn-primary">
            <Plus size={16} /> Register server
          </Link>
        </div>
      </section>

      <div className="kpi-grid">
        <KpiCard icon={Server} label="MCP Servers" value={live.length} percent={pct(active, live.length)} detail={`${active} active · ${live.length - active} inactive`} />
        <KpiCard icon={Activity} label="Availability" value={`${pct(active, live.length)}%`} percent={pct(active, live.length)} detail="Servers enabled on the gateway" tone="green" />
        <KpiCard icon={KeyRound} label="Gateway API Keys" value={liveKeys} percent={pct(liveKeys, keys.length)} detail={`${keys.length - liveKeys} revoked`} tone="cyan" />
        <KpiCard icon={Users} label="Users" value={liveUsers} percent={pct(liveUsers, users.length)} detail={`${users.length - liveUsers} deleted · ${deleted} servers deleted`} tone="indigo" />
      </div>

      <div className="dash-main">
        <section className="card topology">
          <div className="panel-head">
            <div>
              <h3>Gateway Topology</h3>
              <p className="muted">How MCP clients reach your servers through one endpoint</p>
            </div>
            <span className={`health-pill ${health}`}>
              <span className={`pulse ${health}`} />
              <span>{healthLabel}</span>
            </span>
          </div>

          <div className="topo">
            <div className="topo-col">
              <span className="topo-caption">Clients</span>
              <div className="topo-node"><Bot size={16} /> AI agents</div>
              <div className="topo-node"><Laptop size={16} /> IDE &amp; desktop</div>
              <div className="topo-node"><Terminal size={16} /> Scripts &amp; CLIs</div>
            </div>

            <div className="topo-wire"><span>API key</span></div>

            <div className="topo-hub">
              <div className={`hub-core ${health}`}>
                <LogoMark size={40} />
              </div>
              <strong>MCP Gateway</strong>
              <small>{active} of {live.length} servers routed</small>
            </div>

            <div className="topo-wire"><span>MCP</span></div>

            <div className="topo-col servers">
              <span className="topo-caption">Upstream servers</span>
              {topology.length === 0 ? (
                <Link to="/mcp-servers" className="topo-node empty-node">
                  <Plus size={16} /> Register your first server
                </Link>
              ) : (
                topology.map((s) => (
                  <div key={s.id} className={`topo-node ${s.enabled ? '' : 'off'}`} title={s.server_url}>
                    <span className={`dot ${s.enabled ? 'active' : 'inactive'}`} />
                    <span className="topo-name">{s.server_name}</span>
                    <small>{TRANSPORTS[s.transport] || s.transport}</small>
                  </div>
                ))
              )}
              {live.length > TOPOLOGY_LIMIT && (
                <Link to="/mcp-servers" className="link topo-more">+{live.length - TOPOLOGY_LIMIT} more</Link>
              )}
            </div>
          </div>
        </section>

        <section className="card quick-actions">
          <div className="panel-head">
            <h3>Quick Actions</h3>
          </div>
          <div className="action-list">
            {actions.map(({ to, icon: Icon, title, text }) => (
              <Link key={to} to={to} className="action-item">
                <span className="action-icon"><Icon size={18} /></span>
                <span className="action-text">
                  <strong>{title}</strong>
                  <small>{text}</small>
                </span>
                <ArrowRight size={16} className="action-arrow" />
              </Link>
            ))}
          </div>
        </section>
      </div>

      <div className="dash-grid">
        <div className="card panel">
          <div className="panel-head">
            <h3>Servers by Transport</h3>
          </div>
          {live.length === 0 ? (
            <p className="empty">No servers yet</p>
          ) : (
            <div className="bars">
              {byTransport.map((t) => (
                <div key={t.key} className="bar-row">
                  <span className="bar-label">{t.label}</span>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${pct(t.count, live.length)}%` }} />
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
            <p className="empty">No servers yet</p>
          ) : (
            <ul className="recent-list">
              {recent.slice(0, 5).map((s) => {
                const status = s.enabled ? 'active' : 'inactive';
                return (
                  <li key={s.id}>
                    <span className="recent-icon"><Server size={16} /></span>
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
