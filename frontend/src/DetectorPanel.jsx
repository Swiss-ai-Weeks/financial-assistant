import {
  useState,
} from "react";


export default function DetectorPanel({
  onSelectCandidate,
}) {
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
    setRunning(true);
    setError(null);

    try {
      const response = await fetch(
        "/api/anomalies/scan",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({
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
          : "RUN SCAN"}
      </button>


      {error && (
        <div className="scan-error">
          {error}
        </div>
      )}


      {result && (
        <>
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
                  .eligible_fit_count
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
