import { useCallback, useLayoutEffect, useState } from "react";

const STORAGE_KEY = "pythia-theme";

function apply(theme) {
  document.documentElement.dataset.theme = theme;
}

/**
 * Light / dark theme, remembered across visits.
 *
 * Charts read their colours from CSS variables inside their
 * own effects, and React runs a child's effects BEFORE its
 * parent's. The attribute those variables depend on must
 * therefore be in place before any effect runs, or every chart
 * paints itself in the theme that was just left:
 *
 *   - index.html sets it before first paint;
 *   - toggling sets it in the event handler, before re-render;
 *   - the layout effect keeps it true to state, and still runs
 *     ahead of every passive effect.
 */
export function useTheme() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem(STORAGE_KEY) ?? "light"
  );

  useLayoutEffect(() => {
    apply(theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggle = useCallback(() => {
    const next = theme === "light" ? "dark" : "light";

    apply(next);
    setTheme(next);
  }, [theme]);

  return [theme, toggle];
}
