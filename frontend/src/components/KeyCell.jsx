import { useState } from 'react';
import { Check, Copy, Eye, EyeOff } from 'lucide-react';

export default function KeyCell({ value, revealedAll }) {
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const show = revealed || revealedAll;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard blocked */
    }
  };

  return (
    <div className="key-cell">
      <code className="key-value">{show ? value : '•'.repeat(48)}</code>
      <button className="icon-btn subtle" onClick={() => setRevealed((r) => !r)} title={show ? 'Hide key' : 'Show key'}>
        {show ? <Eye size={17} /> : <EyeOff size={17} />}
      </button>
      <button className="icon-btn subtle" onClick={copy} title="Copy key">
        {copied ? <Check size={16} /> : <Copy size={16} />}
      </button>
    </div>
  );
}
