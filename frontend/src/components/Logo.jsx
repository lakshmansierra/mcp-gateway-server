export function LogoMark({ size = 32 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="logo-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#22a6f2" />
          <stop offset="100%" stopColor="#1f62e0" />
        </linearGradient>
      </defs>
      <path d="M16 2l12 7v14l-12 7-12-7V9z" fill="url(#logo-gradient)" />
      <circle cx="16" cy="16" r="5" fill="#fff" />
      <circle cx="16" cy="16" r="2.4" fill="#1f62e0" />
    </svg>
  );
}

export default function Logo({ size = 32, large = false }) {
  return (
    <div className={`logo ${large ? 'logo-large' : ''}`}>
      <LogoMark size={size} />
      <span>MCP Gateway</span>
    </div>
  );
}
