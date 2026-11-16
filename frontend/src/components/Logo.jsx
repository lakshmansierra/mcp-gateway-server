export function LogoMark({ size = 32 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 2l12 7v14l-12 7-12-7V9z" fill="var(--accent)" />
      <circle cx="16" cy="16" r="5" fill="#fff" />
      <circle cx="16" cy="16" r="2.4" fill="var(--accent)" />
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
