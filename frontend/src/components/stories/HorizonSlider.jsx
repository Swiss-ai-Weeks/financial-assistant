const LABELS = { "1h": "1H", "1d": "1D", "1w": "1W", "1m": "1M", "3m": "3M", "1y": "1Y" };

/**
 * The timescale is not a zoom level. Moving it changes what
 * "unusual" means, so every stop shows its own verdict.
 */
export default function HorizonSlider({ ticks, horizon, onChange }) {
  return (
    <div className="horizon" role="radiogroup" aria-label="Horizon">
      <button
        className="horizon__stop"
        disabled
        title="An hourly horizon needs an intraday price feed"
      >
        <span className="horizon__label mono">1H</span>
        <span className="horizon__verdict">no feed</span>
      </button>

      {ticks.map((tick) => (
        <button
          key={tick.horizon}
          role="radio"
          aria-checked={tick.horizon === horizon}
          disabled={!tick.available}
          className={`horizon__stop ${tick.horizon === horizon ? "is-active" : ""} ${
            tick.unusual ? "is-unusual" : ""
          }`}
          onClick={() => onChange(tick.horizon)}
        >
          <span className="horizon__label mono">{LABELS[tick.horizon]}</span>
          <span className="horizon__verdict mono">
            {tick.available ? `${Math.abs(tick.z_score).toFixed(1)}σ` : "—"}
          </span>
        </button>
      ))}
    </div>
  );
}
