import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";

const POLL_MS = 1200;
const ACTIVE = new Set(["queued", "running"]);

/**
 * Follow one investigation until it completes or fails.
 */
export function useInvestigation(investigationId, onSettled) {
  const [latest, setLatest] = useState(null);

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

        if (ACTIVE.has(run.status)) {
          timer = setTimeout(poll, POLL_MS);
        } else {
          settled.current?.(run);
        }
      } catch {
        if (!cancelled) timer = setTimeout(poll, POLL_MS * 2);
      }
    };

    poll();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [investigationId]);

  // A run fetched for a previous id is never shown for the current one.
  return latest?.investigation_id === investigationId ? latest : null;
}
