import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './context/AuthContext.jsx';
import Layout from './components/Layout.jsx';
import Landing from './pages/Landing.jsx';
import AdminLogin from './pages/AdminLogin.jsx';
import Dashboard from './pages/Dashboard.jsx';
import McpServers from './pages/McpServers.jsx';
import DeletedServers from './pages/DeletedServers.jsx';
import GatewayApis from './pages/GatewayApis.jsx';

function RequireSession({ children }) {
  const { role } = useAuth();
  return role ? children : <Navigate to="/" replace />;
}

function RequireAdmin({ children }) {
  const { isAdmin } = useAuth();
  return isAdmin ? children : <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<AdminLogin />} />
      <Route
        element={
          <RequireSession>
            <Layout />
          </RequireSession>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/mcp-servers" element={<McpServers />} />
        <Route path="/gateway-apis" element={<GatewayApis />} />
        <Route
          path="/deleted-servers"
          element={
            <RequireAdmin>
              <DeletedServers />
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
