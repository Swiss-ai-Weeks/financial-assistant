import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Load a resource whenever `key` changes.
 *
 * - A slow response for a previous key never overwrites
 *   the current one: results are stored with their key
 *   and ignored when it no longer matches.
 * - reload() refetches the same key while the previous
 *   data stays on screen.
 */
export function useResource(load, key, { enabled = true } = {}) {
  const [result, setResult] = useState({ key: null, data: null, error: null });
  const [version, setVersion] = useState(0);

  const loader = useRef(load);

  useEffect(() => {
    loader.current = load;
  });

  useEffect(() => {
    if (!enabled) return undefined;

    let cancelled = false;

    loader
      .current()
      .then((data) => {
        if (!cancelled) setResult({ key, data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setResult({ key, data: null, error: error.message });
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, key, version]);

  const reload = useCallback(() => setVersion((value) => value + 1), []);

  const current = enabled && result.key === key;

  return {
    data: current ? result.data : null,
    error: current ? result.error : null,
    loading: enabled && !current,
    reload,
  };
}
