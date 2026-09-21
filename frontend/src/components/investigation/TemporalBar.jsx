import {
  originalCutoff,
  temporalStatuses,
  temporalSummary,
  timelineSteps,
} from "../../lib/claimgraph/temporalModel.js";

function stepLabel(step) {
  if (step.value === "latest") return "Hindsight";
  if (step.label === "At anomaly") return step.label;

  return step.value.slice(0, 10);
}

/**
 * Time travel inside one investigation.
 *
 * The graph is cut at a moment: everything published later
 * disappears from the canvas and from the counts. "At anomaly"
 * is what could have explained the move when it happened;
 * each later step adds what was published by then; hindsight
 * shows it all, and is never evidence.
 */
export default function TemporalBar({ graph, cutoff, onChange, onSelect }) {
  const original = originalCutoff(graph);
  const steps = timelineSteps(graph);

  const then = temporalSummary(graph, original);
  const now = temporalSummary(graph, cutoff || original);

  const before = temporalStatuses(graph, original);

  const later = graph.nodes.filter(
    (node) =>
      node.kind === "document" &&
      before.get(node.node_id) === "appeared_after_cutoff"
  );

  return (
    <div className="temporal">
      <div className="temporal__steps">
        <span className="eyebrow">Evidence as of</span>

        {steps.map((step) => (
          <button
            key={step.value}
            className={`temporal__step mono ${cutoff === step.value ? "is-active" : ""}`}
            title={step.value}
            onClick={() => onChange(step.value)}
          >
            {stepLabel(step)}
          </button>
        ))}
      </div>

      <div className="temporal__figures mono">
        <span title="Evidence public at the anomaly">
          then {then.evidence} · +{then.support} / −{then.counter}
        </span>
        <span title="Evidence public at the selected cutoff">
          shown {now.evidence} · +{now.support} / −{now.counter}
        </span>
        <span>{now.gaps} gaps</span>
      </div>

      {later.length > 0 && (
        <details className="temporal__later">
          <summary>
            {later.length} document{later.length > 1 ? "s" : ""} published after the
            anomaly
          </summary>

          {later.map((node) => (
            <button key={node.node_id} className="link-button" onClick={() => onSelect(node)}>
              {node.label}
            </button>
          ))}

          <p className="muted">
            Later publications are hindsight. They never count as evidence for
            what moved the price.
          </p>
        </details>
      )}
    </div>
  );
}
