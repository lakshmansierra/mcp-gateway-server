import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { KeyRound, LayoutGrid, LogOut, Server, Trash2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';
import Logo from './Logo.jsx';

export default function Layout() {
  const { isAdmin, username, logout } = useAuth();
  const navigate = useNavigate();

  const nav = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutGrid },
    { to: '/mcp-servers', label: 'MCP Servers', icon: Server },
    ...(isAdmin
      ? [{ to: '/deleted-servers', label: 'Deleted Servers', icon: Trash2 }]
      : [{ to: '/gateway-apis', label: 'My Gateway APIs', icon: KeyRound }]),
  ];

  const initials = (username || '?')
    .split(/[.\s_-]+/)
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Logo size={30} />
        </div>
        <nav className="sidebar-nav">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <Icon size={18} strokeWidth={1.75} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-user">
          <div className="avatar">{initials}</div>
          <div className="user-meta">
            <strong>{username}</strong>
            <small>{isAdmin ? 'Admin' : 'User'}</small>
          </div>
          <button className="icon-btn" onClick={handleLogout} title="Log out" aria-label="Log out">
            <LogOut size={18} />
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
