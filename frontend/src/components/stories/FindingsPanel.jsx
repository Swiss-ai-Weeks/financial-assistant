import { money, shortDate, tone } from "../../lib/format";
import { STRATEGY_STYLE } from "../../lib/strategies";

function FindingCard({ finding, selected, onSelect }) {
  const { anomaly } = finding;

  return (
    <button
      className={`finding ${selected ? "is-selected" : ""}`}
      onClick={() => onSelect(anomaly)}
    >
      <div className="finding__head">
        <span className={`chip chip--${anomaly.strategy}`}>
          {STRATEGY_STYLE[anomaly.strategy].label}
        </span>
        <span className={`finding__impact mono ${tone(finding.impact)}`}>
          {finding.impact < 0 ? "−" : "+"}${money(Math.abs(finding.impact))}
        </span>
      </div>

      <h3>{finding.headline}</h3>
      <p>{finding.statement}</p>

      <dl className="finding__facts">
        <dt>Visible since</dt>
        <dd>
          {shortDate(finding.signal_date)} · {finding.sessions_of_warning} sessions
          of warning
        </dd>

        <dt>Likely explanation</dt>
        <dd>
          {finding.explanation ?? (
            <span className="muted">Not investigated yet</span>
          )}
        </dd>

        {finding.confidence && (
          <>
            <dt>Evidence confidence</dt>
            <dd className={`finding__confidence is-${finding.confidence}`}>
              {finding.confidence}
            </dd>
          </>
        )}
      </dl>
    </button>
  );
}

/**
 * Story 1. Not "here are your losers": the abnormal
 * relationships behind them, what they cost, and when
 * they became visible.
 */
export default function FindingsPanel({ postmortem, selectedId, onSelect }) {
  if (!postmortem) {
    return (
      <div className="empty">
        <span className="spinner" /> Reviewing the period…
      </div>
    );
  }

  const relationships = postmortem.findings.filter(
    (finding) => finding.anomaly.strategy === "pairs"
  );

  const signals = postmortem.findings.filter(
    (finding) => finding.anomaly.strategy !== "pairs"
  );

  return (
    <div className="findings">
      <header className="findings__header">
        <h2>What you missed</h2>
        <p className="muted">
          {shortDate(postmortem.window.start)} – {shortDate(postmortem.window.end)} ·{" "}
          {postmortem.findings.length} signals on your holdings
        </p>

        <div className="findings__total">
          <span className="eyebrow">Lost after a signal was already visible</span>
          <span className={`mono ${tone(postmortem.total_impact)}`}>
            {postmortem.total_impact < 0 ? "−" : "+"}$
            {money(Math.abs(postmortem.total_impact))}
          </span>
        </div>
      </header>

      <section>
        <div className="findings__section eyebrow">
          Relationships that broke · {relationships.length}
        </div>

        {relationships.length === 0 && (
          <div className="empty">
            No pair, peer or hedge relationship involving your holdings left its
            historical range in this period.
          </div>
        )}

        {relationships.map((finding) => (
          <FindingCard
            key={finding.anomaly.anomaly_id}
            finding={finding}
            selected={finding.anomaly.anomaly_id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </section>

      <section>
        <div className="findings__section eyebrow">
          Single-name signals · {signals.length}
        </div>

        {signals.map((finding) => (
          <FindingCard
            key={finding.anomaly.anomaly_id}
            finding={finding}
            selected={finding.anomaly.anomaly_id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </section>
    </div>
  );
}
