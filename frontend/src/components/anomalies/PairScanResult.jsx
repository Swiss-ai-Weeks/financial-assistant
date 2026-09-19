import { signed } from "../../lib/format";

/** Outcome of the cointegration scan for the focused tickers. */
export default function PairScanResult({ scan, onSelectPair }) {
  return (
    <section className="scan">
      <div className="scan__header">
        <span className="eyebrow">Pair scan · {scan.focus.join(", ")}</span>
        <span className="muted mono">
          {scan.universe_size} names · fit {scan.formation_start} → {scan.formation_end}
        </span>
      </div>

      {scan.fits.length === 0 ? (
        <p className="scan__empty">
          No cointegrated partner found in the book or the peer universe. Pairs
          trading does not apply to this name.
        </p>
      ) : (
        <table className="table table--compact">
          <thead>
            <tr>
              <th>Pair</th>
              <th className="num">β</th>
              <th className="num">p-value</th>
              <th className="num">Half-life</th>
              <th className="num">Spread z</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {scan.fits.map((fit) => (
              <tr
                key={`${fit.ticker_a}/${fit.ticker_b}`}
                onClick={() => onSelectPair(fit.ticker_a, fit.ticker_b)}
              >
                <td className="mono strong">
                  {fit.ticker_a} / {fit.ticker_b}
                </td>
                <td className="num mono">{fit.beta.toFixed(2)}</td>
                <td className="num mono">{fit.pvalue.toFixed(4)}</td>
                <td className="num mono">
                  {fit.half_life_days ? `${fit.half_life_days.toFixed(1)}d` : "—"}
                </td>
                <td className={`num mono ${fit.flagged ? "down" : ""}`}>
                  {signed(fit.z_score)}
                </td>
                <td className="num">
                  {fit.flagged && <span className="chip chip--pairs">Broken</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
