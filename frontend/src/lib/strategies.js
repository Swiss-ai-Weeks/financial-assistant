/** Presentation metadata for the four strategy monitors. */
export const STRATEGY_STYLE = {
  vwap: { label: "VWAP", color: "--vwap" },
  twap: { label: "TWAP", color: "--twap" },
  trend: { label: "TREND", color: "--trend" },
  pairs: { label: "PAIRS", color: "--pairs" },
};

export const KIND_LABEL = {
  volume_spike: "Volume spike",
  vwap_deviation: "VWAP stretch",
  twap_deviation: "TWAP drift",
  trend_cross: "MA cross",
  trend_whipsaw: "Whipsaw",
  cointegration_spread_deviation: "Spread break",
};

export function cssColor(variable) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();
}
