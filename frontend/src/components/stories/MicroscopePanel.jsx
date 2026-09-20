import { percent, signed } from "../../lib/format";
import OutcomeBar from "./OutcomeBar";

/**
 * Story 2. The first answer is never a company summary. It
 * is: what is unusual about this security, at this horizon.
 */
export default function MicroscopePanel({ microscope, loading, error, onExplain }) {
  if (error) return <div className="error-banner">{error}</div>;

  if (!microscope) {
    return (
      <div className="empty">
        {loading ? (
          <>
            <span className="spinner" /> Measuring…
          </>
        ) : (
          "Pick a security."
        )}
      </div>
    );
  }

  const { reading, peers, latest_anomaly: anomaly } = microscope;

  return (
    <div className="scope">
      <header className="scope__header">
        <span className="eyebrow">
          {microscope.ticker} · {microscope.horizon.toUpperCase()} · as of{" "}
          {microscope.as_of}
        </span>
        <h2>
          {reading.unusual ? "Unusual" : "Nothing unusual"} at this horizon
        </h2>
      </header>

      <ul className="scope__statements">
        {microscope.statements.map((statement) => (
          <li key={statement}>{statement}</li>
        ))}
      </ul>

      <div className="scope__figures mono">
        <div>
          <span className="eyebrow">Return</span>
          {percent(reading.return_pct, 1)}
        </div>
        <div>
          <span className="eyebrow">Market</span>
          {percent(reading.benchmark_return_pct, 1)}
        </div>
        <div>
          <span className="eyebrow">Abnormal</span>
          {percent(reading.abnormal_return_pct, 1)}
        </div>
        <div>
          <span className="eyebrow">Volume</span>
          {reading.volume_multiple.toFixed(1)}×
        </div>
      </div>

      <section className="scope__section">
        <span className="eyebrow">Did its peers follow?</span>

        {peers.length === 0 ? (
          <p className="muted">No close historical peer in the universe.</p>
        ) : (
          <table className="table table--compact">
            <thead>
              <tr>
                <th>Peer</th>
                <th className="num">Co-movement</th>
                <th className="num">Abnormal</th>
                <th className="num">σ</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {peers.map((peer) => (
                <tr key={peer.ticker}>
                  <td className="mono strong">{peer.ticker}</td>
                  <td className="num mono">{peer.correlation.toFixed(2)}</td>
                  <td className="num mono">{percent(peer.abnormal_return_pct, 1)}</td>
                  <td className="num mono">{signed(peer.z_score, 1)}</td>
                  <td className="num">
                    <span className={`chip ${peer.followed ? "" : "chip--trend"}`}>
                      {peer.followed ? "followed" : "did not follow"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="scope__section">
        <span className="eyebrow">What usually happens next?</span>
        <OutcomeBar outcome={microscope.outcome} />
      </section>

      <section className="scope__section">
        <span className="eyebrow">What is driving it?</span>

        {anomaly ? (
          <>
            <p>{anomaly.summary}</p>
            <button className="btn btn--block" onClick={() => onExplain(anomaly)}>
              Explain from the news
            </button>
          </>
        ) : (
          <p className="muted">
            No strategy monitor fired on this security in the review window, so
            there is no anomaly to explain.
          </p>
        )}
      </section>
    </div>
  );
}
