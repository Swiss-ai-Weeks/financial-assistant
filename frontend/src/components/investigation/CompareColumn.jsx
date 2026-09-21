import { compact, signed } from "../../lib/format";
import { Residency } from "./CompareModels";

function duration(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;

  const total = Math.round(seconds);

  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}

function tokenFlow(column) {
  if (!column.prompt_tokens && !column.completion_tokens) return "not reported";

  return `${compact(column.prompt_tokens)} → ${compact(column.completion_tokens)}`;
}

function rank(hypothesis, index) {
  if (index > 0) return `Alternative ${index}`;

  // Ranking first does not mean the evidence backs it.
  return hypothesis.score > 0
    ? "Best supported explanation"
    : "Leading explanation · not supported by the evidence";
}

function Fact({ label, value, className = "" }) {
  return (
    <div className="compare__fact">
      <dt>{label}</dt>
      <dd className={`mono ${className}`}>{value ?? "—"}</dd>
    </div>
  );
}

function Tally({ label, count, className }) {
  if (!count) return null;

  return (
    <span className={`tally ${className}`}>
      {count} {label}
    </span>
  );
}

/** One model's reading of the anomaly. */
export default function CompareColumn({ column, run, retry, onOpen }) {
  const reading = column.status === "queued" || column.status === "running";
  const stage = run?.stages?.find((item) => item.status === "running");

  return (
    <article className={`compare__column is-${column.status}`}>
      <header className="compare__column-head">
        <div>
          <h3>{column.label}</h3>
          {column.model && <p className="compare__model-id mono">{column.model}</p>}
        </div>
        <Residency local={column.local} />
      </header>

      <div className="compare__status">
        {reading && <span className="spinner" />}
        <span className={`mono status status--${column.status}`}>
          {reading ? "reading…" : column.status}
        </span>
        {reading && (
          <span className="muted">{stage?.label ?? "waiting for the model"}</span>
        )}
      </div>

      {column.status === "failed" && (
        <div className="error-banner compare__error">
          {column.error ?? "The run failed without a message."}
        </div>
      )}

      {retry}

      <dl className="compare__facts">
        <Fact label="Duration" value={duration(column.seconds)} />
        <Fact label="Model calls" value={column.calls} />
        <Fact label="Tokens · prompt → completion" value={tokenFlow(column)} />
        <Fact label="Articles used" value={column.documents} />
        <Fact label="Claims" value={column.claims} />
        <Fact label="SEC calculations" value={column.sec} />
        <Fact
          label="Supporting links"
          value={column.supporting}
          className={column.supporting ? "up" : ""}
        />
        <Fact
          label="Countering links"
          value={column.countering}
          className={column.countering ? "down" : ""}
        />
        <Fact label="Open questions" value={column.gaps} />
        <Fact label="Follow-ups" value={column.followups} />
      </dl>

      <div className="compare__explanations">
        <span className="eyebrow">Ranked explanations</span>

        {column.hypotheses.length === 0 ? (
          <p className="compare__note muted">
            {reading
              ? "Nothing ranked yet."
              : "This run produced no explanation."}
          </p>
        ) : (
          <div className="verdicts">
            {column.hypotheses.map((hypothesis, index) => (
              <article
                key={hypothesis.hypothesis_id ?? index}
                className={`verdict compare__verdict ${index === 0 ? "is-leading" : ""}`}
              >
                <div className="verdict__head">
                  <span className="eyebrow">{rank(hypothesis, index)}</span>
                  <span className="mono verdict__score">{signed(hypothesis.score)}</span>
                </div>

                <p className="verdict__text">{hypothesis.text}</p>

                <div className="verdict__tallies mono">
                  <Tally label="support" count={hypothesis.supporting} className="up" />
                  <Tally
                    label="contradict"
                    count={hypothesis.contradicting}
                    className="down"
                  />
                  <Tally label="weaken" count={hypothesis.weakening} className="down" />
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <button
        className="btn btn--ghost btn--small compare__open"
        disabled={!column.has_graph || !run}
        title={column.has_graph ? undefined : "This run has no ClaimGraph"}
        onClick={() => onOpen(run)}
      >
        Open ClaimGraph
      </button>
    </article>
  );
}
