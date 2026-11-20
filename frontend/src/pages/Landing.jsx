import { useNavigate } from 'react-router-dom';
import { ArrowRight, Shield, User } from 'lucide-react';
import Logo from '../components/Logo.jsx';
import { useAuth } from '../context/AuthContext.jsx';

export default function Landing() {
  const navigate = useNavigate();
  const { notice } = useAuth();

  return (
    <div className="auth-page">
      <header className="auth-header">
        <Logo size={40} large />
      </header>

      {notice && <div className="alert-info auth-notice">{notice}</div>}

      <div className="choice-grid">
        <div className="card choice-card">
          <div className="icon-tile">
            <Shield size={24} strokeWidth={1.75} />
          </div>
          <h3>Admin Portal</h3>
          <p className="muted">Register and manage MCP servers, user accounts and gateway API keys.</p>
          <button className="btn btn-primary btn-block" onClick={() => navigate('/login')}>
            Login <ArrowRight size={17} />
          </button>
        </div>

        <div className="card choice-card">
          <div className="icon-tile neutral">
            <User size={24} strokeWidth={1.75} />
          </div>
          <h3>User Access</h3>
          <p className="muted">Sign in with the account your admin created and generate gateway API keys for their MCP servers.</p>
          <button className="btn btn-outline btn-block" onClick={() => navigate('/user-login')}>
            Login <ArrowRight size={17} />
          </button>
        </div>
      </div>
    </div>
  );
}
