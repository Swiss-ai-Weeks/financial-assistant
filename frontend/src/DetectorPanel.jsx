import {
  useState,
} from "react";


export default function DetectorPanel({
  onSelectCandidate, sharedAsOf, onAsOf,
}) {
  const [mode, setMode] = useState("live");
  const [asOf, setAsOf] = useState("2026-08-28");
  const [entry, setEntry] =
    useState(1.5);

  const [corrMin, setCorrMin] =
    useState(0.65);

  const [alpha, setAlpha] =
    useState(0.05);

  const [result, setResult] =
    useState(null);

  const [running, setRunning] =
    useState(false);

  const [error, setError] =
    useState(null);


  async function runScan() {
    onSelectCandidate?.(null);
    setResult(null);
    setRunning(true);
    setError(null);

    try {
      const response = await fetch(
        mode === "historical" ? "/api/anomalies/historical-scan" : "/api/anomalies/scan",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({
            as_of: sharedAsOf ?? asOf,
            entry,
            corr_min: corrMin,
            alpha,
          }),
        },
      );

      const payload =
        await response.json();

      if (!response.ok) {
        throw new Error(
          payload.error
          ?? "Anomaly scan failed"
        );
      }

      setResult(payload);

    } catch (err) {
      setError(err.message);

    } finally {
      setRunning(false);
    }
  }


  return (
    <aside className="detector-panel">
      <div className="detector-kicker">
        OBSERVE
      </div>

      <h2>Anomaly detector</h2>
      <label>Mode<select value={mode} disabled={running} onChange={e => {setMode(e.target.value); setResult(null); onSelectCandidate?.(null);}}>
        <option value="live">Live</option><option value="historical">Time Travel</option>
      </select></label>
      {mode === 'historical' && <label>Time Travel · As-of date<input type="date" value={sharedAsOf ?? asOf} disabled={running}
        onChange={e => {setAsOf(e.target.value); onAsOf?.(e.target.value); setResult(null); onSelectCandidate?.(null);}} /></label>}

      <p className="detector-description">
        Configure which statistical
        deviations become investigation
        candidates.
      </p>


      <label className="detector-control">
        <div>
          <span>Z threshold</span>

          <strong>
            {entry.toFixed(2)}
          </strong>
        </div>

        <input
          type="range"
          min="1"
          max="3"
          step="0.05"
          value={entry}
          onChange={(event) =>
            setEntry(
              Number(
                event.target.value
              )
            )
          }
        />
      </label>


      <label className="detector-control">
        <div>
          <span>
            Minimum correlation
          </span>

          <strong>
            {corrMin.toFixed(2)}
          </strong>
        </div>

        <input
          type="range"
          min="0.50"
          max="0.90"
          step="0.01"
          value={corrMin}
          onChange={(event) =>
            setCorrMin(
              Number(
                event.target.value
              )
            )
          }
        />
      </label>


      <label className="detector-control">
        <div>
          <span>
            Cointegration p
          </span>

          <strong>
            {alpha.toFixed(3)}
          </strong>
        </div>

        <input
          type="range"
          min="0.005"
          max="0.10"
          step="0.005"
          value={alpha}
          onChange={(event) =>
            setAlpha(
              Number(
                event.target.value
              )
            )
          }
        />
      </label>


      <button
        className="scan-button"
        onClick={runScan}
        disabled={running}
      >
        {running
          ? "SCANNING…"
          : mode === "historical" ? "TRAVEL TO DATE" : "RUN SCAN"}
      </button>


      {error && (
        <div className="scan-error">
          {error}
        </div>
      )}


      {result && (
        <>
          <p>Market state as of {result.as_of}{result.resolved_session && <> · Resolved session: {result.resolved_session}<br />
            Formation: {result.formation_start} through {result.formation_end}<br />
            Price observations through: {result.price_observations_through}. No future price rows used. Fits recomputed.<br />
            {result.universe_limitation}</>}</p>
          <h3>{result.resolved_session ? 'Anomalies on this date' : 'Current anomalies'}</h3>
          <div className="detector-stats">
            <div>
              <span>Securities</span>
              <strong>
                {
                  result.cache
                  .price_securities
                }
              </strong>
            </div>

            <div>
              <span>Relationships</span>
              <strong>
                {
                  result
                  .eligible_fit_count ?? "Recomputed"
                }
              </strong>
            </div>

            <div>
              <span>Anomalies</span>
              <strong>
                {
                  result
                  .candidate_count
                }
              </strong>
            </div>

            <div>
              <span>Runtime</span>
              <strong>
                {result.elapsed_ms} ms
              </strong>
            </div>
          </div>


          <div className="candidate-list">
            {result.candidates.map(
              (candidate) => (
                <button
                  type="button"
                  className="candidate-card"
                  key={candidate.pair}
                  onClick={() =>
                    onSelectCandidate?.(
                      candidate
                    )
                  }
                >
                  <div className="candidate-title">
                    <strong>
                      {candidate.pair}
                    </strong>

                    <span>
                      {candidate.signal_date}
                    </span>
                  </div>

                  <div className="candidate-values">
                    <span>
                      z{" "}
                      <b>
                        {
                          candidate
                          .z_score
                          .toFixed(2)
                        }
                      </b>
                    </span>

                    <span>
                      r{" "}
                      <b>
                        {
                          candidate
                          .correlation
                          .toFixed(2)
                        }
                      </b>
                    </span>

                    <span>
                      p{" "}
                      <b>
                        {
                          candidate
                          .cointegration_p
                          .toFixed(3)
                        }
                      </b>
                    </span>
                  </div>
                </button>
              )
            )}
          </div>
        </>
      )}
    </aside>
  );
}
