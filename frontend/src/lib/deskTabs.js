/**
 * The tabs of the desk's two panels, per view.
 *
 * Past and Now share the panels but not their tabs ("Peers ×
 * timescales" exists only in Now, "Positions" only in Past),
 * and the chosen tab is remembered across views and reloads.
 * A remembered tab the current view does not have must never
 * be rendered: its panel waits for data that view never loads.
 */
export const BOTTOM_TABS = {
  copilot: ["peers", "anomalies"],
  postmortem: ["anomalies", "positions", "news", "investigations"],
};

export const SIDE_TABS = {
  copilot: ["findings", "news", "explain"],
  postmortem: ["findings", "monitors", "news", "explain"],
};

/** The remembered tab when this view has it, else the view's first. */
export function resolveTab(tabs, view, wanted) {
  const keys = tabs[view] ?? tabs.postmortem;

  return keys.includes(wanted) ? wanted : keys[0];
}
