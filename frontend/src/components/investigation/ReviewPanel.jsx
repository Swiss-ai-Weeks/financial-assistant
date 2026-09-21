import {
  graphCounts,
  labelFor,
  requirementCoverage,
  summaryFor,
} from "../../lib/claimgraph/reviewModel.js";
import ReviewActions from "./ReviewActions";

const CLAIM_KINDS = ["hypothesis", "primary_claim", "claim", "subclaim"];

/**
 * The case as a reviewer reads it: the explanation under
 * review, what supports and counters it at the chosen cutoff,
 * what is assumed and what is missing, and the decisions
 * people have recorded.
 */
export default function ReviewPanel({
  graph,
  review,
  persistence,
  onChange,
  onAction,
  onSelect,
  onExport,
}) {
  const counts = graphCounts(graph);
  const coverage = requirementCoverage(graph);
  const summary = summaryFor(graph, review.claim_id);

  const choices = graph.nodes.filter((node) => CLAIM_KINDS.includes(node.kind));

  const sections = [
    ["Supporting", summary.supporting],
    ["Countering", summary.counter],
    ["Assumptions", summary.assumptions],
    ["Missing evidence", summary.missing],
    ["Calculations", summary.calculations],
    ["Sources", summary.sources],
  ];

  return (
    <div className="review">
      <header className="review__header">
        <div>
          <span className="eyebrow">Evidence review · {review.review_id}</span>
          <h2>{review.title}</h2>
        </div>
        <span className={`chip review__status review__status--${review.status}`}>
          {labelFor(review.status)}
        </span>
      </header>

      <div className="review__fields">
        <label>
          <span className="eyebrow">Title</span>
          <input
            value={review.title}
            onChange={(event) => onChange({ title: event.target.value })}
          />
        </label>
        <label>
          <span className="eyebrow">Reviewer</span>
          <input
            value={review.owner}
            placeholder="Your name"
            onChange={(event) => onChange({ owner: event.target.value })}
          />
        </label>
        <label>
          <span className="eyebrow">Purpose</span>
          <input
            value={review.purpose}
            onChange={(event) => onChange({ purpose: event.target.value })}
          />
        </label>
        <button className="btn btn--ghost btn--small" onClick={onExport}>
          Export review + graph
        </button>
      </div>

      <dl className="review__counts">
        {Object.entries(counts).map(([label, count]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="mono">{count}</dd>
          </div>
        ))}
      </dl>

      <p className="muted review__note">
        Counts are unique items at the inspection cutoff; one item may both
        support one explanation and counter another.{" "}
        {coverage.total > 0 &&
          `${coverage.satisfied}/${coverage.total} evidence requirements recorded as satisfied. `}
        {persistence}
      </p>

      <label className="review__claim">
        <span className="eyebrow">Explanation under review</span>
        <select
          value={review.claim_id ?? ""}
          onChange={(event) => onChange({ claim_id: event.target.value })}
        >
          {choices.length === 0 && <option value="">None recorded</option>}
          {choices.map((node) => (
            <option key={node.node_id} value={node.node_id}>
              {node.label}
            </option>
          ))}
        </select>
      </label>

      <div className="review__grid">
        {sections.map(([title, nodes]) => (
          <section key={title}>
            <span className="eyebrow">
              {title} · {nodes.length}
            </span>

            {nodes.length === 0 && (
              <p className="muted">None recorded. Not evidence of absence.</p>
            )}

            {nodes.map((node) => (
              <button
                key={node.node_id}
                className="link-button"
                onClick={() => onSelect(node)}
              >
                {node.label}
              </button>
            ))}
          </section>
        ))}
      </div>

      <ReviewActions state={review.status} onAction={onAction} />

      <p className="muted review__note">
        Approval records that a person accepts this analysis for the stated
        purpose. It does not establish truth and it does not close evidence
        gaps.
      </p>

      <details className="review__history">
        <summary>Decision history · {review.history.length}</summary>

        {review.history.map((entry, index) => (
          <div key={index} className="review__entry">
            <strong>{labelFor(entry.status)}</strong>
            <span className="muted mono">
              {entry.reviewer} · {new Date(entry.at).toLocaleString()}
            </span>
            <p>{entry.note}</p>
            <small className="muted">{entry.item ?? `purpose: ${entry.purpose}`}</small>
          </div>
        ))}
      </details>
    </div>
  );
}
