import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { CloverIcon } from "../icons";
import OutcomeBar from "./OutcomeBar";

function Funnel({ steps }) {
  const largest = Math.max(...steps.map((step) => step.count), 1);

  return (
    <ol className="funnel">
      {steps.map((step, index) => (
        <li key={step.label} style={{ animationDelay: `${index * 140}ms` }}>
          <span className="funnel__count mono">{step.count.toLocaleString("en-US")}</span>
          <span className="funnel__label">
            {step.label}
            {step.detail && <small className="funnel__detail">{step.detail}</small>}
          </span>
          <span
            className="funnel__bar"
            style={{
              // Log scale: the funnel spans three orders of magnitude.
              width: `${(Math.log10(step.count + 1) / Math.log10(largest + 1)) * 100}%`,
            }}
          />
        </li>
      ))}
    </ol>
  );
}

const VERDICTS = {
  lasting_event: "Lasting event",
  transient_event: "Transient event",
  no_event: "No identifiable event",
};

/**
 * Nemotron's reading of the headlines behind the move, with
 * the headline it rests on. Without a reading the card says
 * what it does know instead of pretending.
 */
function WhyNow({ setup }) {
  const { triage } = setup;

  if (!triage) {
    return (
      <p className="muted">
        {setup.headlines} headlines named these companies before the evidence
        cutoff. Nemotron has not read them: whether one justifies the gap is
        what the reasoning view answers.
      </p>
    );
  }

  return (
    <div className="triage">
      <div className="triage__head">
        <span className={`chip triage__verdict is-${triage.verdict}`}>
          {VERDICTS[triage.verdict]}
        </span>
        <span className="muted mono">
          read by {triage.model.split("/").pop()} · {setup.headlines} headlines
        </span>
      </div>

      <p>{triage.why_now}</p>

      {triage.headline && (
        <a
          className="triage__source mono"
          href={triage.headline.url}
          target="_blank"
          rel="noreferrer"
        >
          {triage.headline.publisher ?? "Source"} · {triage.headline.title}
        </a>
      )}
    </div>
  );
}

function SetupCard({ setup, asOf, label, leading, onReason }) {
  return (
    <article className={`setup ${leading ? "is-leading" : ""}`}>
      <span className="eyebrow">{label}</span>

      <h2 className="mono">
        LONG {setup.long} / SHORT {setup.short}
      </h2>

      <div className="setup__figures mono">
        <div>
          <span className="eyebrow">Anomaly</span>
          {Math.abs(setup.z_score).toFixed(1)}σ
        </div>
        <div>
          <span className="eyebrow">Analogues</span>
          {setup.outcome?.analogues ?? 0}
        </div>
        <div>
          <span className="eyebrow">Horizon</span>
          {setup.expected_horizon}
        </div>
        <div>
          <span className="eyebrow">Liquidity</span>${Math.round(setup.liquidity_musd)}M/day
        </div>
      </div>

      <section>
        <span className="eyebrow">Why now</span>
        <p>{setup.anomaly.summary}.</p>
        <WhyNow setup={setup} />
      </section>

      <section>
        <span className="eyebrow">What usually happens next</span>
        <OutcomeBar
          outcome={setup.outcome}
          labels={{ continuation: "Kept widening", reversion: "Converged" }}
          favourable="reversion"
        />
      </section>

      <section>
        <span className="eyebrow">Why these securities are connected</span>
        <ul>
          {setup.why_connected.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </section>

      <section>
        <span className="eyebrow">What would invalidate it</span>
        <ul>
          {setup.invalidation.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </section>

      <footer className="setup__footer">
        <span className="muted mono">Evidence available as of {asOf} close</span>
        <button className="btn" onClick={() => onReason(setup.anomaly)}>
          Show me the reasoning
        </button>
      </footer>
    </article>
  );
}

/**
 * Story 3. Nobody asked about anything: the pipeline runs
 * backwards, from the whole market down to one setup.
 */
const POLL_MS = 1500;

export default function DiscoveryView({ onReason }) {
  const [job, setJob] = useState({ status: "idle" });
  const timer = useRef(null);

  // A scan runs in the background on the server: it can take
  // minutes, longer than a proxy keeps one request open. The
  // page polls, so it also picks up a scan that is already
  // running or already finished when it is opened.
  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const next = await api.discovery();

        if (cancelled) return;

        setJob(next);

        if (next.status === "running") timer.current = setTimeout(poll, POLL_MS);
      } catch (error) {
        if (!cancelled) setJob({ status: "failed", error: error.message });
      }
    };

    poll();

    return () => {
      cancelled = true;
      clearTimeout(timer.current);
    };
  }, []);

  const scan = async () => {
    clearTimeout(timer.current);

    try {
      setJob(await api.startDiscovery());
    } catch (error) {
      setJob({ status: "failed", error: error.message });
      return;
    }

    const poll = async () => {
      try {
        const next = await api.discovery();

        setJob(next);

        if (next.status === "running") timer.current = setTimeout(poll, POLL_MS);
      } catch {
        // The desk may be restarting: keep trying.
        timer.current = setTimeout(poll, POLL_MS * 2);
      }
    };

    timer.current = setTimeout(poll, POLL_MS);
  };

  const state = job;
  const { discovery } = job;

  return (
    <div className="discovery">
      <header className="discovery__hero">
        <span className="eyebrow">Market → anomalies → causes → analogues → one idea</span>
        <h1>What should I be looking at?</h1>

        <button
          className="btn discovery__button"
          disabled={state.status === "running"}
          onClick={scan}
        >
          <CloverIcon size={20} />
          {state.status === "running" ? "Scanning the universe…" : "I’m Feeling Lucky"}
        </button>

        {state.status === "running" && (
          <p className="discovery__stage">
            <span className="spinner" /> {state.stage}
          </p>
        )}

        {state.status === "failed" && <div className="error-banner">{state.error}</div>}
      </header>

      {discovery && (
        <div className="discovery__body">
          <aside>
            <Funnel steps={discovery.funnel} />
            <p className="muted discovery__basis">
              Analogue base: {discovery.analogue_breaks} out-of-sample relationship
              breaks, {discovery.analogue_period}. Each was found using only the
              year before it, then followed forward.
            </p>
          </aside>

          <main>
            {discovery.setups.length === 0 ? (
              <div className="setup">
                <h2>Nothing new clears the bar today</h2>
                <p className="muted">
                  No relationship outside your book is unusual, liquid and
                  favourable in the historical record. Saying so is part of
                  the product.
                </p>
              </div>
            ) : (
              discovery.setups.map((setup, index) => (
                <SetupCard
                  key={setup.anomaly.anomaly_id}
                  setup={setup}
                  asOf={discovery.as_of}
                  label={index === 0 ? "🍀 Today’s discovery" : "Also surfaced"}
                  leading={index === 0}
                  onReason={onReason}
                />
              ))
            )}

            {discovery.repriced.length > 0 && (
              <section className="discovery__known">
                <span className="eyebrow">
                  Dropped by Nemotron · the gap looks like a justified repricing
                </span>

                {discovery.repriced.map((setup) => (
                  <button
                    key={setup.anomaly.anomaly_id}
                    className="discovery__known-row"
                    onClick={() => onReason(setup.anomaly)}
                  >
                    <span className="mono strong">
                      {setup.long} / {setup.short}
                    </span>
                    <span className="mono">{Math.abs(setup.z_score).toFixed(1)}σ</span>
                    <span className="muted">{setup.triage.why_now}</span>
                  </button>
                ))}
              </section>
            )}

            {discovery.on_your_desk.length > 0 && (
              <section className="discovery__known">
                <span className="eyebrow">
                  Already on your desk · reported in your post-mortem
                </span>

                {discovery.on_your_desk.map((setup) => (
                  <button
                    key={setup.anomaly.anomaly_id}
                    className="discovery__known-row"
                    onClick={() => onReason(setup.anomaly)}
                  >
                    <span className="mono strong">
                      {setup.long} / {setup.short}
                    </span>
                    <span className="mono">{Math.abs(setup.z_score).toFixed(1)}σ</span>
                    <span className="muted">
                      Involves a holding, so it is not news to you. Open it in
                      Past →
                    </span>
                  </button>
                ))}
              </section>
            )}

            <p className="muted discovery__disclaimer">
              A research signal built from historical frequencies. Not investment
              advice.
            </p>
          </main>
        </div>
      )}
    </div>
  );
}
