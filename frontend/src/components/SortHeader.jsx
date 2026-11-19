import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';

export function useSort(rows, initialKey, initialDir = 'desc') {
  const [sort, setSort] = useState({ key: initialKey, dir: initialDir });

  const sorted = useMemo(() => {
    const out = [...rows];
    out.sort((a, b) => {
      const av = a[sort.key] ?? '';
      const bv = b[sort.key] ?? '';
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv), undefined, { sensitivity: 'base' });
      return sort.dir === 'asc' ? cmp : -cmp;
    });
    return out;
  }, [rows, sort]);

  const toggle = (key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));

  return { sorted, sort, toggle };
}

export default function SortHeader({ label, field, sort, onSort }) {
  const active = sort.key === field;
  const Icon = active && sort.dir === 'desc' ? ArrowDown : ArrowUp;
  return (
    <th>
      <button className={`th-sort ${active ? 'active' : ''}`} onClick={() => onSort(field)}>
        {label}
        <Icon size={13} />
      </button>
    </th>
  );
}
