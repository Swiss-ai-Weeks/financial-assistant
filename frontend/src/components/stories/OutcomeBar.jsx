import { percent } from "../../lib/format";

function tint(key, favourable) {
  if (key === "indeterminate") return "neutral";

  return key === favourable ? "good" : "bad";
}

/**
 * "What usually happens next", as historical frequencies.
 * The sample size is always shown next to the percentages.
 */
// For a single security, continuing is neither good nor
// bad. For a relationship, converging is what the setup
// needs, so the caller says which outcome is favourable.
export default function OutcomeBar({ outcome, labels, favourable = "continuation" }) {
  if (!outcome) {
    return (
      <p className="muted outcome__none">
        Fewer than five comparable past situations: not enough to say what
        usually follows.
      </p>
    );
  }

  const parts = [
    { key: "continuation", label: labels?.continuation ?? "Continuation", value: outcome.continuation_pct },
    { key: "reversion", label: labels?.reversion ?? "Mean reversion", value: outcome.reversion_pct },
    { key: "indeterminate", label: "Indeterminate", value: outcome.indeterminate_pct },
  ];

  return (
    <div className="outcome">
      <div className="outcome__bar">
        {parts.map((part) => (
          <div
            key={part.key}
            className={`outcome__part outcome__part--${tint(part.key, favourable)}`}
            style={{ width: `${part.value}%` }}
          />
        ))}
      </div>

      <dl className="outcome__legend mono">
        {parts.map((part) => (
          <div key={part.key}>
            <dt>
              <i className={`outcome__swatch outcome__part--${tint(part.key, favourable)}`} />
              {part.label}
            </dt>
            <dd>{Math.round(part.value)}%</dd>
          </div>
        ))}
      </dl>

      <p className="outcome__basis">
        Next {outcome.forward_sessions} trading days ·{" "}
        <strong>{outcome.analogues} historical analogues</strong> · expected{" "}
        {percent(outcome.expected_abnormal_return_pct)} · {outcome.scope}.
        Historical frequencies, not a forecast.
      </p>
    </div>
  );
}
