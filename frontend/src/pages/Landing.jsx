import { useNavigate } from 'react-router-dom';
import { ArrowRight, Shield, User } from 'lucide-react';
import AuthShell from '../components/AuthShell.jsx';
import { useAuth } from '../context/AuthContext.jsx';

const OPTIONS = [
  {
    to: '/login',
    icon: Shield,
    title: 'Admin Portal',
    text: 'Register and manage MCP servers, user accounts and gateway API keys.',
    tone: '',
  },
  {
    to: '/user-login',
    icon: User,
    title: 'User Access',
    text: 'Sign in with the account your admin created and generate gateway API keys for their MCP servers.',
    tone: 'neutral',
  },
];

export default function Landing() {
  const navigate = useNavigate();
  const { notice } = useAuth();

  return (
    <AuthShell>
      <div className="auth-panel">
        <div className="auth-panel-head">
          <h2>Welcome</h2>
          <p className="muted">Choose how you want to sign in.</p>
        </div>

        {notice && <div className="alert-info">{notice}</div>}

        <div className="choice-list">
          {OPTIONS.map(({ to, icon: Icon, title, text, tone }) => (
            <button key={to} className="choice-card" onClick={() => navigate(to)}>
              <span className={`icon-tile ${tone}`}>
                <Icon size={22} strokeWidth={1.75} />
              </span>
              <span className="choice-text">
                <strong>{title}</strong>
                <small>{text}</small>
              </span>
              <ArrowRight size={18} className="choice-arrow" />
            </button>
          ))}
        </div>
      </div>
    </AuthShell>
  );
}
