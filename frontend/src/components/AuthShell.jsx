import { Activity, KeyRound, Network, ShieldCheck } from 'lucide-react';
import Logo from './Logo.jsx';

const FEATURES = [
  { icon: Network, title: 'One endpoint, every server', text: 'Aggregate all your MCP servers behind a single Streamable HTTP endpoint.' },
  { icon: KeyRound, title: 'Scoped API keys', text: 'Each key sees only the servers it is allowed to reach.' },
  { icon: Activity, title: 'Self-healing connections', text: 'Health checks and automatic reconnects keep tools available.' },
];

/** Split-screen frame for the landing and login pages: brand panel on the left, content on the right. */
export default function AuthShell({ children }) {
  return (
    <div className="auth-shell">
      <aside className="auth-brand">
        <Logo size={36} />

        <div className="auth-brand-body">
          <span className="eyebrow light">
            <ShieldCheck size={14} /> Enterprise MCP Gateway
          </span>
          <h1>
            One gateway.
            <br />
            <span className="gradient-text">Every MCP server.</span>
          </h1>
          <p>Register servers, govern access with API keys, and give every AI client a single secure endpoint.</p>

          <ul className="feature-list">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title}>
                <span className="feature-icon"><Icon size={18} /></span>
                <div>
                  <strong>{title}</strong>
                  <small>{text}</small>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <small className="auth-brand-foot">Secured with token authentication · SAP BTP</small>
      </aside>

      <main className="auth-content">{children}</main>
    </div>
  );
}
