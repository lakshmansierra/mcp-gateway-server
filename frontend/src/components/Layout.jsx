import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  BarChart3,
  Wrench,
  KeyRound,
  LayoutGrid,
  LogOut,
  Menu,
  Server,
  Settings,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';
import { checkHealth, GATEWAY_MCP_URL } from '../services/mcpService.js';
import AccountModal from './AccountModal.jsx';
import { CopyButton } from './GenerateApiModal.jsx';
import Logo from './Logo.jsx';

const ADMIN_NAV = [
  { section: 'Overview', items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutGrid }] },
  {
    section: 'Infrastructure',
    items: [
      { to: '/mcp-servers', label: 'MCP Servers', icon: Server },
      { to: '/tools', label: 'Tools', icon: Wrench },
      { to: '/deleted-servers', label: 'Deleted Servers', icon: Trash2 },
    ],
  },
  {
    section: 'Access Control',
    items: [
      { to: '/users', label: 'Users', icon: Users },
      { to: '/gateway-apis', label: 'Gateway APIs', icon: KeyRound },
    ],
  },
  { section: 'Monitoring', items: [{ to: '/usage', label: 'Tool Usage', icon: BarChart3 }] },
];

const USER_NAV = [
  {
    section: 'Access',
    items: [
      { to: '/gateway-apis', label: 'My Gateway APIs', icon: KeyRound },
      { to: '/tools', label: 'Servers & Tools', icon: Wrench },
    ],
  },
  { section: 'Monitoring', items: [{ to: '/usage', label: 'My Usage', icon: BarChart3 }] },
];

const HEALTH_TEXT = { checking: 'Checking', ok: 'Operational', down: 'Unreachable' };
const HEALTH_POLL_MS = 60_000;
const COLLAPSE_KEY = 'mcp_gateway_sidebar_collapsed';

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1';
  } catch {
    return false;
  }
}

export default function Layout() {
  const { isAdmin, username, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [showAccount, setShowAccount] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [health, setHealth] = useState('checking');
  const menuRef = useRef(null);

  const nav = isAdmin ? ADMIN_NAV : USER_NAV;
  const current = nav.flatMap((g) => g.items.map((i) => ({ ...i, section: g.section }))).find((i) => pathname.startsWith(i.to));

  const refreshHealth = useCallback(async () => {
    setHealth('checking');
    try {
      const h = await checkHealth();
      setHealth(h?.status === 'ok' ? 'ok' : 'down');
    } catch {
      setHealth('down');
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    const timer = setInterval(refreshHealth, HEALTH_POLL_MS);
    return () => clearInterval(timer);
  }, [refreshHealth]);

  useEffect(() => {
    setDrawerOpen(false);
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const close = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    const onKey = (e) => e.key === 'Escape' && setMenuOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  const toggleCollapsed = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1');
      } catch {
        /* storage unavailable */
      }
      return !c;
    });
  };

  const initials = (username || '?')
    .split(/[.\s_-]+/)
    .filter(Boolean)
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const handleLogout = async () => {
    setLeaving(true);
    await logout();
    navigate('/');
  };

  return (
    <div className={`app-shell ${collapsed ? 'is-collapsed' : ''}`}>
      {drawerOpen && <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} />}

      <aside className={`sidebar ${drawerOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <Logo size={30} />
          <button className="icon-btn drawer-close" onClick={() => setDrawerOpen(false)} aria-label="Close menu">
            <X size={18} />
          </button>
        </div>

        <nav className="sidebar-nav">
          {nav.map((group) => (
            <div key={group.section} className="nav-group">
              <div className="nav-label">{group.section}</div>
              {group.items.map(({ to, label, icon: Icon }) => (
                <NavLink key={to} to={to} title={collapsed ? label : undefined} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                  <Icon size={18} strokeWidth={1.75} />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-endpoint">
          <div className="endpoint-head">
            <span className={`pulse ${health}`} />
            <span>Gateway {HEALTH_TEXT[health].toLowerCase()}</span>
          </div>
          <div className="endpoint-url">
            <code title={GATEWAY_MCP_URL}>{GATEWAY_MCP_URL || 'Endpoint not configured'}</code>
            {GATEWAY_MCP_URL && <CopyButton text={GATEWAY_MCP_URL} label="Copy gateway endpoint" />}
          </div>
        </div>

        <button className="collapse-btn" onClick={toggleCollapsed} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
          <span>Collapse</span>
        </button>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setDrawerOpen(true)} aria-label="Open menu">
            <Menu size={20} />
          </button>

          <nav className="breadcrumbs" aria-label="Breadcrumb">
            <span>Console</span>
            {current && (
              <>
                <ChevronRight size={14} />
                <span>{current.section}</span>
                <ChevronRight size={14} />
                <strong>{current.label}</strong>
              </>
            )}
          </nav>

          <div className="topbar-right">
            <button className={`health-pill ${health}`} onClick={refreshHealth} title="Backend & database status. Click to re-check.">
              <span className={`pulse ${health}`} />
              <span>API {HEALTH_TEXT[health]}</span>
            </button>

            <div className="user-menu" ref={menuRef}>
              <button className="user-trigger" onClick={() => setMenuOpen((o) => !o)} aria-haspopup="menu" aria-expanded={menuOpen}>
                <span className="avatar">{initials}</span>
                <span className="user-meta">
                  <strong>{username}</strong>
                  <small>{isAdmin ? 'Administrator' : 'User'}</small>
                </span>
                <ChevronDown size={16} className="chev" />
              </button>
              {menuOpen && (
                <div className="menu" role="menu">
                  <div className="menu-head">
                    <span className="avatar lg">{initials}</span>
                    <div>
                      <strong>{username}</strong>
                      <small>{isAdmin ? 'Administrator' : 'User'}</small>
                    </div>
                  </div>
                  <button
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      setShowAccount(true);
                    }}
                  >
                    <Settings size={16} /> Account settings
                  </button>
                  <button role="menuitem" className="danger" onClick={handleLogout} disabled={leaving}>
                    <LogOut size={16} /> {leaving ? 'Signing out...' : 'Log out'}
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="main">
          <Outlet context={{ health, refreshHealth }} />
        </main>
      </div>

      {showAccount && <AccountModal onClose={() => setShowAccount(false)} />}
    </div>
  );
}
