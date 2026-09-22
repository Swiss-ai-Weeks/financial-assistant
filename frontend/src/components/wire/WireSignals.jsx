import { shortDate } from "../../lib/format";

const WIDTH = 900;
const HEIGHT = 220;
const PAD = { left: 40, right: 16, top: 16, bottom: 28 };

/**
 * One bar per session: the mean surprise of that day's edges
 * (how much of the news the model did not expect), with the
 * day's largest surprise as a tick and the memory drift as a
 * line. Historical readings of the model, not a forecast.
 */
export default function WireSignals({ ticker, holdings, rows, loading, error, onSelectTicker }) {
  if (error) return <div className="error-banner">{error}</div>;
  if (loading && !rows) return <div className="empty"><span className="spinner" /> Reading {ticker}…</div>;

  const days = rows ?? [];
  const inner = { w: WIDTH - PAD.left - PAD.right, h: HEIGHT - PAD.top - PAD.bottom };
  const step = days.length ? inner.w / days.length : 0;
  const y = (v) => PAD.top + inner.h - v * inner.h;
  const maxDrift = Math.max(0.05, ...days.map((d) => d.drift ?? 0));

  const top = [...days].sort((a, b) => b.surprise_mean - a.surprise_mean).slice(0, 5);

  return (
    <div className="signals">
      <div className="seg seg--wrap">
        {(holdings ?? []).map((h) => (
          <button key={h.ticker} className={`seg__item mono ${h.ticker === ticker ? "is-active" : ""}`} onClick={() => onSelectTicker(h.ticker)}>
            {h.ticker}
          </button>
        ))}
      </div>

      {!days.length ? (
        <div className="empty">No scored days for {ticker}. Run <code>make wire-score</code> after training.</div>
      ) : (
        <>
          <svg className="signals__chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`Surprise per day for ${ticker}`}>
            {[0, 0.5, 1].map((v) => (
              <g key={v}>
                <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(v)} y2={y(v)} className="signals__grid" />
                <text x={PAD.left - 6} y={y(v) + 4} textAnchor="end" className="signals__axis mono">{v.toFixed(1)}</text>
              </g>
            ))}

            {days.map((d, i) => (
              <g key={d.day} transform={`translate(${PAD.left + i * step},0)`}>
                <rect
                  x={step * 0.15}
                  width={Math.max(1, step * 0.7)}
                  y={y(d.surprise_mean)}
                  height={inner.h - (y(d.surprise_mean) - PAD.top)}
                  className={`signals__bar ${d.surprise_mean >= 0.6 ? "is-high" : ""}`}
                />
                <line x1={step * 0.5} x2={step * 0.5} y1={y(d.surprise_max)} y2={y(d.surprise_max) + 3} className="signals__max" />
                <title>{`${d.day}: mean surprise ${d.surprise_mean.toFixed(2)}, max ${d.surprise_max.toFixed(2)}, ${d.edges} edges${d.drift != null ? `, drift ${d.drift.toFixed(3)}` : ""}`}</title>
              </g>
            ))}

            <polyline
              className="signals__drift"
              points={days
                .filter((d) => d.drift != null)
                .map((d) => `${PAD.left + days.indexOf(d) * step + step / 2},${y(Math.min(1, d.drift / maxDrift))}`)
                .join(" ")}
            />

            {days.filter((_, i) => i % Math.max(1, Math.floor(days.length / 8)) === 0).map((d) => (
              <text key={d.day} x={PAD.left + days.indexOf(d) * step + step / 2} y={HEIGHT - 8} textAnchor="middle" className="signals__axis mono">
                {shortDate(d.day)}
              </text>
            ))}
          </svg>

          <ul className="legend">
            <li><span className="legend__bar" /> mean surprise of the day's edges</li>
            <li><span className="legend__tick" /> the day's most surprising edge</li>
            <li><span className="legend__line legend__line--drift" /> memory drift (scaled to its max, {maxDrift.toFixed(3)})</li>
          </ul>

          <section>
            <span className="eyebrow">Most surprising days</span>
            <table className="table">
              <thead>
                <tr><th>Day</th><th>Mean surprise</th><th>Max</th><th>Edges</th><th>Drift</th></tr>
              </thead>
              <tbody>
                {top.map((d) => (
                  <tr key={d.day} className="mono">
                    <td>{shortDate(d.day)}</td>
                    <td>{d.surprise_mean.toFixed(2)}</td>
                    <td>{d.surprise_max.toFixed(2)}</td>
                    <td>{d.edges}</td>
                    <td>{d.drift != null ? d.drift.toFixed(3) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
