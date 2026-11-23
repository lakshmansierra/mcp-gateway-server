import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Run `fetcher` (an async function) on mount and whenever `deps` change; keep its result in state.
 * Returns { data, error, loading, reload }. `data` keeps the last good value while reloading, so tables don't
 * flash empty. A slower, older request can't overwrite the result of a newer one.
 */
export function useLoader(fetcher, deps = [], initial = null) {
  const [state, setState] = useState({ data: initial, error: '', loading: true });
  const seq = useRef(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  const reload = useCallback(async () => {
    const mine = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: '' }));
    try {
      const data = await run();
      if (mine === seq.current) setState({ data, error: '', loading: false });
    } catch (err) {
      if (mine === seq.current) setState((s) => ({ ...s, error: err.message || String(err), loading: false }));
    }
  }, [run]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { ...state, reload };
}
