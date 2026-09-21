import {
  labelFor,
  nodeData,
  provenanceFor,
  sourceCategory,
} from "../../lib/claimgraph/reviewModel.js";
import {
  originalCutoff,
  temporalStatuses,
} from "../../lib/claimgraph/temporalModel.js";
import { BoltIcon } from "../icons";
import { kindLabel } from "./graphAdapter";
import ReviewActions from "./ReviewActions";

const OPEN_KINDS = ["missing_evidence", "evidence_requirement"];
const EPISTEMIC = ["supports", "weakens", "contradicts", "context_for"];

const HIDDEN_FIELDS = [
  "inspectorType",
  "displayKind",
  "label",
  "edge_id",
  "node_id",
  "kind",
  "support",
  "counter",
  "humanState",
  "temporalStatus",
];

function isLink(key, value) {
  return ["url", "source_uri"].includes(key) && /^https?:\/\//i.test(String(value));
}

function Value({ name, value }) {
  if (value === null || value === undefined || value === "") return "—";

  if (isLink(name, value)) {
    return (
      <a href={String(value)} target="_blank" rel="noreferrer">
        Open source ↗
      </a>
    );
  }

  if (typeof value === "object") {
    return <pre className="inspector-json">{JSON.stringify(value, null, 2)}</pre>;
  }

  return String(value);
}

function Rows({ data }) {
  return Object.entries(data)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => (
      <div className="inspector-row" key={key}>
        <span>{labelFor(key)}</span>
        <strong>
          <Value name={key} value={value} />
        </strong>
      </div>
    ));
}

function Section({ title, children }) {
  return (
    <section className="inspector-section">
      <span className="eyebrow">{title}</span>
      {children}
    </section>
  );
}

/**
 * Everything the graph records about one node or relation:
 * what it says, when it became public, which evidence it
 * stands on, which model run produced it, and what a person
 * decided about it. Hidden and future items stay inspectable,
 * because an audit has to be able to see what was excluded.
 */
export default function NodeInspector({
  node,
  graph,
  cutoff = "latest",
  reviewState,
  followUp,
  onSelect,
  onAction,
  onClose,
}) {
  if (!node) {
    return (
      <aside className="inspector">
        <div className="node-type">Inspector</div>
        <h2>Select a node or relationship</h2>
        <p className="muted">
          Inspect what was observed, reported, assumed or inferred; why evidence
          relates to a hypothesis; and which model run produced it.
        </p>
        <p className="muted">
          Roles belong to relationships: one item can support one explanation
          and weaken another.
        </p>
      </aside>
    );
  }

  const isEdge = node.inspectorType === "edge";

  const details = isEdge
    ? Object.fromEntries(
        Object.entries(node).filter(([key]) => !HIDDEN_FIELDS.includes(key))
      )
    : (node.data ?? {});

  const byId = (id) => graph.nodes.find((item) => item.node_id === id);
  const select = (id) => byId(id) && onSelect(byId(id));

  const provenance = isEdge
    ? { relationships: [], sources: [], runs: [] }
    : provenanceFor(graph, node);

  const open = !isEdge && OPEN_KINDS.includes(node.kind);
  const financial = details.metadata?.metric_id || details.metadata?.concept
    ? details.metadata
    : null;

  const status = isEdge
    ? "both ends must be public"
    : labelFor(temporalStatuses(graph, cutoff).get(node.node_id));

  return (
    <aside className="inspector">
      <div className="inspector__top">
        <div className="node-type">
          {isEdge ? "Relationship" : kindLabel(node.kind)}
        </div>
        {onClose && (
          <button className="inspector__close" onClick={onClose} aria-label="Close inspector">
            ✕
          </button>
        )}
      </div>

      <h2>{node.label ?? labelFor(node.kind)}</h2>

      {open && (
        <Section title={`Open question · ${labelFor(details.resolution_status ?? "unresolved")}`}>
          {details.resolution && (
            <p className="inspector__note">
              {details.resolution.summary}
              {details.resolution.remaining_question && (
                <>
                  {" "}
                  <strong>Still unknown:</strong>{" "}
                  {details.resolution.remaining_question}
                </>
              )}
            </p>
          )}

          {["supporting_item_ids", "contradicting_item_ids"].map((field) =>
            details.resolution?.[field]?.length ? (
              <div key={field} className="inspector__links">
                <small>{field.startsWith("supporting") ? "Found" : "Counterpoint"}</small>
                {details.resolution[field].map((id) => (
                  <button key={id} className="link-button" onClick={() => select(id)}>
                    {byId(id)?.label ?? id}
                  </button>
                ))}
              </div>
            ) : null
          )}

          <button
            className="btn btn--block"
            disabled={!followUp || followUp.disabled}
            title={followUp?.reason}
            onClick={() => followUp.start(node.node_id)}
          >
            <BoltIcon size={15} />
            {followUp?.running ? "Researching…" : "Investigate this question"}
          </button>

          <p className="muted">
            One bounded cycle: the news cache, the web and SEC filings are
            searched again for this question only. A new question needs a new
            decision from you.
          </p>

          {(details.followup_history ?? []).length > 0 && (
            <div className="inspector__links">
              <small>Earlier follow-ups</small>
              {details.followup_history.map((id) => (
                <button key={id} className="link-button" onClick={() => select(id)}>
                  {id}
                </button>
              ))}
            </div>
          )}
        </Section>
      )}

      <Section title="When it became public">
        <Rows
          data={{
            status_at_cutoff: status,
            inspection_cutoff: cutoff === "latest" ? "latest (hindsight)" : cutoff,
            published_at: details.published_date_only
              ? `${String(details.published_at).slice(0, 10)} (date only)`
              : details.published_at,
            observed_at: details.observed_at ?? originalCutoff(graph),
            retrieved_at: details.retrieved_at,
          }}
        />
        <p className="muted">
          Retrieval time never establishes publication time.
        </p>
      </Section>

      {isEdge && EPISTEMIC.includes(node.kind) && (
        <Section title="Evidence assessment">
          <Rows
            data={{
              evidence: byId(node.source)?.label,
              evidence_kind: kindLabel(byId(node.source)?.kind),
              relation: labelFor(node.kind),
              explanation: byId(node.target)?.label,
              strength: details.strength,
              rationale: details.rationale,
              assumptions: details.assumptions,
              missing_information: details.missing_information,
              model_run: details.model_run_id,
            }}
          />
        </Section>
      )}

      {isEdge && (
        <div className="inspector__ends">
          <button className="btn btn--ghost btn--small" onClick={() => select(node.source)}>
            ← Source
          </button>
          <span className="mono">{labelFor(node.kind)}</span>
          <button className="btn btn--ghost btn--small" onClick={() => select(node.target)}>
            Target →
          </button>
        </div>
      )}

      {financial && (
        <Section title="Financial evidence">
          <Rows
            data={{
              metric: financial.display_name ?? financial.concept,
              value:
                financial.value == null
                  ? "unavailable"
                  : financial.unit === "ratio"
                    ? `${(financial.value * 100).toFixed(2)}%`
                    : `${Number(financial.value).toLocaleString()} ${financial.unit ?? ""}`,
              period: [financial.period_start, financial.period_end]
                .filter(Boolean)
                .join(" → "),
              compared_with: financial.comparison_period,
              formula: financial.formula,
              form: financial.form,
              filed_at: financial.filed_at,
              accession: financial.accession,
              public_since: financial.available_at,
              warnings: financial.warnings,
            }}
          />
        </Section>
      )}

      {!isEdge && (
        <Section title="Relationships">
          {provenance.relationships.length === 0 && (
            <p className="muted">None recorded.</p>
          )}

          {provenance.relationships.map((edge) => {
            const outgoing = edge.source === node.node_id;
            const other = byId(outgoing ? edge.target : edge.source);

            return (
              <div className="inspector__relation" key={edge.edge_id}>
                <button
                  className={`chip chip--relation chip--${edge.kind}`}
                  onClick={() => onSelect({ ...edge, inspectorType: "edge" })}
                >
                  {outgoing ? "→" : "←"} {labelFor(edge.kind)}
                </button>
                <button className="link-button" onClick={() => other && onSelect(other)}>
                  {other?.label ?? "unresolved reference"}
                </button>
              </div>
            );
          })}
        </Section>
      )}

      {!isEdge && (
        <Section title="Sources">
          {provenance.sources.length === 0 && (
            <p className="muted">No linked source document.</p>
          )}

          {provenance.sources.map((source) => (
            <div className="inspector__relation" key={source.node_id}>
              <button className="link-button" onClick={() => onSelect(source)}>
                {source.label}
              </button>
              <small className="muted">{sourceCategory(source)}</small>
              {nodeData(source).url && (
                <a href={nodeData(source).url} target="_blank" rel="noreferrer">
                  ↗
                </a>
              )}
            </div>
          ))}
        </Section>
      )}

      {!isEdge && provenance.runs.length > 0 && (
        <Section title="Produced by">
          {provenance.runs.map((run) => {
            const data = nodeData(run);

            return (
              <div className="inspector__relation" key={run.node_id}>
                <button className="link-button" onClick={() => onSelect(run)}>
                  {labelFor(data.operation ?? run.label)}
                </button>
                <small className="muted mono">
                  {String(data.model ?? "").split("/").pop()}
                  {data.latency_ms != null && ` · ${(data.latency_ms / 1000).toFixed(1)}s`}
                  {data.completion_tokens != null && ` · ${data.completion_tokens} tok`}
                </small>
              </div>
            );
          })}
        </Section>
      )}

      <details className="inspector__raw">
        <summary>Recorded fields</summary>
        <Rows data={{ [isEdge ? "edge_id" : "node_id"]: node.edge_id ?? node.node_id, ...details }} />
      </details>

      {onAction && (
        <ReviewActions item={node} state={reviewState} onAction={onAction} />
      )}
    </aside>
  );
}
