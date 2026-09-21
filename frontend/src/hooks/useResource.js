import { useCallback, useEffect, useRef, useState } from "react";

import { resourceCache } from "../lib/resourceCache";

const DEFAULT_MAX_AGE = 60_000;

/**
 * Load a resource whenever `key` changes.
 *
 * - A slow response for a previous key never overwrites
 *   the current one: results are stored with their key
 *   and ignored when it no longer matches.
 * - reload() refetches the same key while the previous
 *   data stays on screen.
 * - Answers are remembered (see lib/resourceCache): a key
 *   seen before is shown at once, whichever view asks, and
 *   is only fetched again once it is older than `maxAge`.
 *   With `persist` it also survives a reload of the page.
 */
export function useResource(
  load,
  key,
  { enabled = true, maxAge = DEFAULT_MAX_AGE, persist = false } = {}
) {
  const [result, setResult] = useState({ key: null, data: null, error: null });
  const [version, setVersion] = useState(0);

  // Which (key, version) last finished, so "refreshing" can be
  // derived instead of being set from inside the effect.
  const [finished, setFinished] = useState(null);

  const loader = useRef(load);
  const forced = useRef(0);

  useEffect(() => {
    loader.current = load;
  });

  const token = `${key}#${version}`;

  useEffect(() => {
    if (!enabled) return undefined;

    let cancelled = false;

    const done = () => {
      if (!cancelled) setFinished(token);
    };

    // A forced reload always fetches; otherwise a remembered
    // answer that is still fresh is enough.
    const force = version > 0 && forced.current === version;

    if (!force && resourceCache.isFresh(key, maxAge)) {
      Promise.resolve().then(done);

      return () => {
        cancelled = true;
      };
    }

    loader
      .current()
      .then((data) => {
        resourceCache.write(key, data, { persist });

        if (!cancelled) setResult({ key, data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setResult({ key, data: null, error: error.message });
      })
      .finally(done);

    return () => {
      cancelled = true;
    };
  }, [enabled, key, version, token, maxAge, persist]);

  const reload = useCallback(() => {
    setVersion((value) => {
      forced.current = value + 1;

      return value + 1;
    });
  }, []);

  // What this hook fetched for the key wins; before that,
  // whatever any view remembered about it. A failed refresh
  // keeps showing what was known.
  const own = enabled && result.key === key ? result : null;
  const known = enabled ? resourceCache.read(key) : null;

  const data = own?.data ?? known?.data ?? null;

  return {
    data,
    error: data == null ? (own?.error ?? null) : null,
    loading: enabled && data == null && own?.error == null,
    refreshing: enabled && finished !== token,
    reload,
  };
}
