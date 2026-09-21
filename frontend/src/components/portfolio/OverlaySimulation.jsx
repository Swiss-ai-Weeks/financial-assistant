import { useRef, useState } from "react";

import { api } from "../../api/client";
import { percent, tone } from "../../lib/format";
import { NOTICE, pairCandidates } from "../../lib/portfolio";
import MetricValue from "./MetricValue";

const HORIZONS = [1, 5, 20, 63];

const SAMPLES = [
  ["current", () => "Current book"],
  ["candidate_performance", (a, b) => `Candidate ${a} vs ${b}`],
  ["combined", () => "Book + overlay"],
];

function Legs({ securities, market }) {
  return (
    <table className="table table--compact portfolio-sim__legs">
      <thead>
        <tr>
          <th>Leg</th>
          {HORIZONS.map((sessions) => (
            <th key={sessions} className="num">
              {sessions}D
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Object.entries(securities ?? {}).map(([ticker, security]) => {
          const missing = security?.status === "unavailable" ? security : null;

          return (
            <tr key={ticker}>
              <td className="mono strong">{ticker}</td>
              {HORIZONS.map((sessions) => (
                <td key={sessions} className="num">
                  <MetricValue metric={missing ?? security?.[`return_${sessions}`]} compact />
                </td>
              ))}
            </tr>
          );
        })}

        {market?.relative_returns && (
          <tr>
            <td className="muted">A minus B</td>
            {HORIZONS.map((sessions) => {
              const value = market.relative_returns[sessions]?.value;

              return (
                <td key={sessions} className={`num mono ${tone(value)}`}>
                  {Number.isFinite(value) ? percent(value * 100) : "—"}
                </td>
              );
            })}
          </tr>
        )}
      </tbody>
    </table>
  );
}

function Provenance({ simulation }) {
  const { provenance } = simulation;

  return (
    <details className="portfolio-provenance">
      <summary className="eyebrow">Calculation provenance</summary>

      <dl>
        <dt>Formula</dt>
        <dd className="mono">{simulation.formula ?? "—"}</dd>

        <dt>Formula version</dt>
        <dd className="mono">{provenance?.formula_version ?? simulation.formula_version ?? "—"}</dd>

        <dt>Evidence cutoff</dt>
        <dd className="mono">{provenance?.as_of_cutoff ?? "—"}</dd>

        <dt>Prices</dt>
        <dd className="mono">
          {provenance?.source ?? "—"} · {provenance?.price_field ?? "—"} · annualised on{" "}
          {provenance?.annualization ?? "—"} sessions
        </dd>

        <dt>Input SHA-256</dt>
        <dd className="mono portfolio-provenance__hash">{provenance?.input_sha256 ?? "—"}</dd>

        {provenance?.observations && (
          <>
            <dt>Observations</dt>
            <dd className="mono">
              {Object.entries(provenance.observations)
                .map(([ticker, count]) => `${ticker} ${count}`)
                .join(" · ")}
            </dd>
          </>
        )}

        <dt>Assumptions</dt>
        <dd>
          <ul>
            {(provenance?.assumptions ?? []).map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </dd>
      </dl>
    </details>
  );
}

function Result({ run }) {
  const { simulation, market, a, b } = run;
  const { correlation, current } = simulation;

  return (
    <div className="portfolio-sim__result">
      <header>
        <h3 className="mono">
          {a} vs {b} · {(simulation.gross_overlay * 100).toFixed(1)}% gross
        </h3>
        <p className="muted mono">
          {current.start} → {current.end} · {current.sessions} common sessions
        </p>
      </header>

      <p>{simulation.construction}.</p>

      <table className="table portfolio-sim__table">
        <thead>
          <tr>
            <th>Sample</th>
            <th className="num">Return</th>
            <th className="num">Annualised volatility</th>
            <th className="num">Max drawdown</th>
          </tr>
        </thead>
        <tbody>
          {SAMPLES.map(([key, label]) => (
            <tr key={key}>
              <td>{label(a, b)}</td>
              <td className="num">
                <MetricValue metric={simulation[key]?.return_window} compact />
              </td>
              <td className="num">
                <MetricValue metric={simulation[key]?.volatility} toned={false} plain compact />
              </td>
              <td className="num">
                <MetricValue metric={simulation[key]?.max_drawdown} compact />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="portfolio-sim__correlation">
        <span className="eyebrow">Candidate / book correlation</span>
        {correlation?.status === "available" ? (
          <span className="mono strong">{correlation.value.toFixed(3)}</span>
        ) : (
          <span className="portfolio-na">{correlation?.reason ?? "Not calculated"}</span>
        )}
        <span className="muted">Pearson, aligned daily returns of the same sample.</span>
      </p>

      <section>
        <span className="eyebrow">Recent return decomposition</span>
        <Legs securities={simulation.securities} market={market} />
      </section>

      {simulation.remaining_question && (
        <section className="portfolio-sim__unknown">
          <span className="eyebrow">Still unknown</span>
          <p>{simulation.remaining_question}</p>
        </section>
      )}

      <Provenance simulation={simulation} />
    </div>
  );
}

/**
 * What the book would have looked like with a small
 * A-relative-to-B overlay on top. The scenario is analytical:
 * a spread anomaly is no authority for a trade direction, so
 * nothing here says which leg to buy.
 *
 * A result belongs to the book it was calculated on. It is
 * labelled with its own inputs, so editing the form does not
 * hide it, but it disappears when the book or the replay
 * date changes: those numbers no longer describe this book.
 */
export default function OverlaySimulation({ portfolio, anomalies, bookId, asOf }) {
  const pairs = pairCandidates(anomalies);

  // Drafts only: until the manager types, the legs follow the
  // most severe pair anomaly, which can arrive after the page.
  const [legs, setLegs] = useState({});
  const [gross, setGross] = useState("2");
  const [lookback, setLookback] = useState("252");

  const [run, setRun] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // A slow answer to an earlier click must not replace a later one.
  const latest = useRef(0);

  const a = (legs.a ?? pairs[0]?.a ?? "").trim().toUpperCase();
  const b = (legs.b ?? pairs[0]?.b ?? "").trim().toUpperCase();

  const grossValue = Number(gross);
  const lookbackValue = Number(lookback);

  const problem =
    (!a || !b ? "Name both legs." : null) ??
    (a === b ? "The two legs must differ." : null) ??
    (gross === "" || !(grossValue >= 0 && grossValue <= 100)
      ? "Gross overlay must be between 0 and 100%."
      : null) ??
    (!Number.isInteger(lookbackValue) || lookbackValue < 20 || lookbackValue > 252
      ? "Lookback must be 20 to 252 sessions."
      : null);

  const held = (portfolio?.positions ?? []).filter((position) =>
    [a, b].includes(position.ticker)
  );

  const context = `${bookId}|${asOf ?? "live"}`;
  const result = run?.context === context ? run : null;

  const simulate = async () => {
    const ticket = (latest.current += 1);

    setBusy(true);
    setError(null);

    try {
      // The relative returns are context, not the result:
      // losing them must not lose the simulation.
      const [simulation, market] = await Promise.all([
        api.simulateOverlay(a, b, grossValue / 100, lookbackValue),
        api.marketContext([a, b]).catch(() => null),
      ]);

      if (ticket !== latest.current) return;

      if (simulation.status === "available") {
        setRun({
          context,
          a,
          b,
          simulation,
          market: market?.status === "unavailable" ? null : market,
        });
      } else {
        setRun(null);
        setError(`Simulation unavailable: ${simulation.reason ?? "no reason given"}`);
      }
    } catch (failure) {
      if (ticket === latest.current) setError(failure.message);
    } finally {
      if (ticket === latest.current) setBusy(false);
    }
  };

  return (
    <div className="portfolio-sim">
      <p className="portfolio-notice" role="note">
        {NOTICE}
      </p>

      {pairs.length > 0 && (
        <div className="portfolio-sim__picks">
          <span className="eyebrow">Pair anomalies on the book</span>

          {pairs.slice(0, 8).map((pair) => (
            <button
              key={`${pair.a}/${pair.b}`}
              className={`chip portfolio-sim__pick ${pair.a === a && pair.b === b ? "is-active" : ""}`}
              title={pair.anomaly.summary}
              onClick={() => setLegs({ a: pair.a, b: pair.b })}
            >
              {pair.a} / {pair.b}
              {pair.z_score != null && <span> · {Math.abs(pair.z_score).toFixed(1)}σ</span>}
            </button>
          ))}
        </div>
      )}

      <form
        className="portfolio-sim__form"
        onSubmit={(event) => {
          event.preventDefault();

          if (!problem && !busy) simulate();
        }}
      >
        <label className="portfolio-field">
          <span className="eyebrow">Ticker A</span>
          <input
            className="mono"
            value={legs.a ?? pairs[0]?.a ?? ""}
            placeholder="e.g. KO"
            spellCheck={false}
            onChange={(event) =>
              setLegs((previous) => ({ ...previous, a: event.target.value.toUpperCase() }))
            }
          />
        </label>

        <span className="portfolio-sim__versus muted">relative to</span>

        <label className="portfolio-field">
          <span className="eyebrow">Ticker B</span>
          <input
            className="mono"
            value={legs.b ?? pairs[0]?.b ?? ""}
            placeholder="e.g. PEP"
            spellCheck={false}
            onChange={(event) =>
              setLegs((previous) => ({ ...previous, b: event.target.value.toUpperCase() }))
            }
          />
        </label>

        <label className="portfolio-field portfolio-field--narrow">
          <span className="eyebrow">Gross overlay (%)</span>
          <input
            className="mono"
            type="number"
            min="0"
            max="100"
            step="0.5"
            value={gross}
            onChange={(event) => setGross(event.target.value)}
          />
        </label>

        <label className="portfolio-field portfolio-field--narrow">
          <span className="eyebrow">Lookback (sessions)</span>
          <input
            className="mono"
            type="number"
            min="20"
            max="252"
            step="1"
            value={lookback}
            onChange={(event) => setLookback(event.target.value)}
          />
        </label>

        <button className="btn" type="submit" disabled={busy || problem != null}>
          {busy && <span className="spinner" />}
          {busy ? "Simulating…" : "Simulate against the book"}
        </button>
      </form>

      <p className="muted portfolio-sim__overlap">
        {problem ??
          (!portfolio ? "Loading the book…" : null) ??
          (held.length
            ? `Book overlap: ${held
                .map((position) => `${position.ticker} ${position.weight_pct.toFixed(1)}%`)
                .join(" · ")}. The overlay is added on top of the unchanged book.`
            : "Neither leg is held: the overlay is added on top of the unchanged book.")}
      </p>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {run && !result && (
        <p className="muted">
          The book or the replay date changed since the last simulation. Run it
          again: those figures described another book.
        </p>
      )}

      {result && <Result run={result} />}
    </div>
  );
}
