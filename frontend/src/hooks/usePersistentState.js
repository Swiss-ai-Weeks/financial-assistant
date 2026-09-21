import { useCallback, useState } from "react";

const PREFIX = "pythia:ui:";

function read(name, fallback) {
  try {
    const raw = localStorage.getItem(PREFIX + name);

    return raw == null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

/**
 * useState that survives a reload of the page.
 *
 * Where the manager was (which view, which ticker, which tabs,
 * which graphs were open) is part of the work. Losing it on
 * every refresh made the desk feel like it restarted.
 * `valid` rejects a stored value that no longer makes sense.
 * `override`, when given, wins over what was stored: a deep
 * link says where to be, whatever was remembered.
 */
export function usePersistentState(
  name,
  fallback,
  valid = () => true,
  override = undefined
) {
  const [value, setValue] = useState(() => {
    if (override !== undefined) return override;

    const stored = read(name, fallback);

    return valid(stored) ? stored : fallback;
  });

  const set = useCallback(
    (next) => {
      setValue((current) => {
        const resolved = typeof next === "function" ? next(current) : next;

        try {
          if (resolved === undefined || resolved === null) {
            localStorage.removeItem(PREFIX + name);
          } else {
            localStorage.setItem(PREFIX + name, JSON.stringify(resolved));
          }
        } catch {
          // Private mode or a full quota: the state still
          // works for this visit.
        }

        return resolved;
      });
    },
    [name]
  );

  return [value, set];
}
