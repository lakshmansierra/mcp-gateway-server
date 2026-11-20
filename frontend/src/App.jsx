import { Navigate, Route, Routes } from 'react-router-dom';
import { homeFor, useAuth } from './context/AuthContext.jsx';
import Layout from './components/Layout.jsx';
import Landing from './pages/Landing.jsx';
import AdminLogin from './pages/AdminLogin.jsx';
import Dashboard from './pages/Dashboard.jsx';
import McpServers from './pages/McpServers.jsx';
import DeletedServers from './pages/DeletedServers.jsx';
import GatewayApis from './pages/GatewayApis.jsx';
import Users from './pages/Users.jsx';

function RequireSession({ children }) {
  const { role } = useAuth();
  return role ? children : <Navigate to="/" replace />;
}

function RequireAdmin({ children }) {
  const { isAdmin, role } = useAuth();
  return isAdmin ? children : <Navigate to={homeFor(role)} replace />;
}

/** Signed-in visitors skip the landing and login pages. */
function GuestOnly({ children }) {
  const { role } = useAuth();
  return role ? <Navigate to={homeFor(role)} replace /> : children;
}

const admin = (el) => <RequireAdmin>{el}</RequireAdmin>;

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<GuestOnly><Landing /></GuestOnly>} />
      <Route path="/login" element={<GuestOnly><AdminLogin mode="admin" /></GuestOnly>} />
      <Route path="/user-login" element={<GuestOnly><AdminLogin mode="user" /></GuestOnly>} />
      <Route
        element={
          <RequireSession>
            <Layout />
          </RequireSession>
        }
      >
        <Route path="/dashboard" element={admin(<Dashboard />)} />
        <Route path="/mcp-servers" element={admin(<McpServers />)} />
        <Route path="/deleted-servers" element={admin(<DeletedServers />)} />
        <Route path="/users" element={admin(<Users />)} />
        <Route path="/gateway-apis" element={<GatewayApis />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
