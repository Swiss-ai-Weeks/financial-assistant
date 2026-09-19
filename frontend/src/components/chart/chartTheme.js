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
    timeScale: { borderColor: cssColor("--border"), rightOffset: 4 },
  };
}

/** lightweight-charts reports a day as a string or as {year, month, day}. */
export function toIsoDay(time) {
  if (time == null) return null;
  if (typeof time === "string") return time;

  const pad = (value) => String(value).padStart(2, "0");

  return `${time.year}-${pad(time.month)}-${pad(time.day)}`;
}
