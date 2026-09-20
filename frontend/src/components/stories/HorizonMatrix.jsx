const LABELS = { "1d": "1D", "1w": "1W", "1m": "1M", "3m": "3M", "1y": "1Y" };

/** Cell tint grows with |σ|, red below normal and green above. */
function tint(z) {
  if (z == null) return undefined;

  const strength = Math.min(Math.abs(z) / 4, 1);
  const token = z < 0 ? "--down" : "--up";

  return `color-mix(in srgb, var(${token}) ${Math.round(strength * 70)}%, transparent)`;
}

/**
 * The security and its historical peers, each read at every
 * horizon. A row that is hot alone is a stock-specific move;
 * a hot column is the whole group moving at that timescale.
 */
export default function HorizonMatrix({ microscope, horizon, onHorizon, onSelectTicker }) {
  if (!microscope) {
    return <div className="empty">Measuring…</div>;
  }

  const horizons = microscope.ticks.map((tick) => tick.horizon);

  return (
    <table className="table matrix">
      <thead>
        <tr>
          <th>Security</th>
          <th className="num">Co-movement</th>
          {horizons.map((name) => (
            <th
              key={name}
              className={`num matrix__head ${name === horizon ? "is-active" : ""}`}
              onClick={() => onHorizon(name)}
            >
              {LABELS[name]}
            </th>
          ))}
          <th>Reading</th>
        </tr>
      </thead>
      <tbody>
        {microscope.matrix.map((row) => {
          const unusualAt = row.ticks.filter((tick) => tick.unusual);

          return (
            <tr
              key={row.ticker}
              className={row.is_subject ? "is-selected" : ""}
              onClick={() => onSelectTicker(row.ticker)}
            >
              <td className="mono strong">{row.ticker}</td>
              <td className="num mono">
                {row.is_subject ? "—" : row.correlation.toFixed(2)}
              </td>

              {row.ticks.map((tick) => (
                <td
                  key={tick.horizon}
                  className={`num mono matrix__cell ${
                    tick.horizon === horizon ? "is-active" : ""
                  }`}
                  style={{ background: tint(tick.z_score) }}
                >
                  {tick.available
                    ? `${tick.z_score >= 0 ? "+" : "−"}${Math.abs(tick.z_score).toFixed(1)}σ`
                    : "—"}
                </td>
              ))}

              <td className="muted">
                {unusualAt.length === 0
                  ? "Ordinary at every timescale"
                  : `Unusual at ${unusualAt.map((t) => LABELS[t.horizon]).join(", ")}`}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
