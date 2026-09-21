import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { resourceCache } from "../lib/resourceCache";

const POLL_MS = 1200;
const ACTIVE = new Set(["queued", "running"]);

const cacheKey = (id) => `investigation:${id}`;

export function isActive(run) {
  return (
    run != null &&
    (ACTIVE.has(run.status) ||
      (run.followups ?? []).some((followup) => ACTIVE.has(followup.status)))
  );
}

/**
 * Follow one investigation until it, and any follow-up on it,
 * completes or fails.
 *
 * A settled run is remembered across reloads: reopening a
 * ClaimGraph shows it at once and checks the server behind
 * the scenes, instead of waiting for a few hundred kilobytes
 * every time the view is entered.
 */
export function useInvestigation(investigationId, onSettled) {
  const [latest, setLatest] = useState(
    () => (investigationId && resourceCache.read(cacheKey(investigationId))?.data) || null
  );
  const [version, setVersion] = useState(0);

  const settled = useRef(onSettled);

  useEffect(() => {
    settled.current = onSettled;
  });

  useEffect(() => {
    if (!investigationId) return undefined;

    let cancelled = false;
    let timer;

    const poll = async () => {
      try {
        const run = await api.investigation(investigationId);

        if (cancelled) return;

        setLatest(run);

        if (isActive(run)) {
          timer = setTimeout(poll, POLL_MS);
        } else {
          resourceCache.write(cacheKey(investigationId), run, { persist: true });
          settled.current?.(run);
        }
      } catch {
        if (!cancelled) timer = setTimeout(poll, POLL_MS * 2);
      }
    };

    const known = resourceCache.read(cacheKey(investigationId))?.data;

    // Remembered and settled: show it, verify once, no polling.
    Promise.resolve().then(() => {
      if (cancelled) return;

      if (known) setLatest(known);

      poll();
    });

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [investigationId, version]);

  // After starting a follow-up the run is active again.
  const refresh = useCallback(() => setVersion((value) => value + 1), []);

  // A run fetched for a previous id is never shown for the current one.
  const run = latest?.investigation_id === investigationId ? latest : null;

  return [run, refresh];
}
