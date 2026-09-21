import { ColorType, CrosshairMode } from "lightweight-charts";

import { cssColor } from "../../lib/strategies";

/** Chart options derived from the current CSS theme tokens. */
export function chartOptions() {
  return {
    layout: {
      background: { type: ColorType.Solid, color: cssColor("--bg") },
      textColor: cssColor("--text-muted"),
      fontFamily: cssColor("--font-mono"),
      fontSize: 12,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: cssColor("--border") },
      horzLines: { color: cssColor("--border") },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: cssColor("--border") },
    // The latest session is the right edge of what exists, so
    // it stays put: zooming with the wheel reveals more history
    // on the LEFT instead of sliding the present away, and the
    // chart cannot be dragged into an empty future or past.
    timeScale: {
      borderColor: cssColor("--border"),
      rightOffset: 4,
      rightBarStaysOnScroll: true,
      fixRightEdge: true,
      fixLeftEdge: true,
    },
  };
}

/** lightweight-charts reports a day as a string or as {year, month, day}. */
export function toIsoDay(time) {
  if (time == null) return null;
  if (typeof time === "string") return time;

  const pad = (value) => String(value).padStart(2, "0");

  return `${time.year}-${pad(time.month)}-${pad(time.day)}`;
}
