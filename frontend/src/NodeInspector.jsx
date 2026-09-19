function formatKey(key) {
  return key
    .replaceAll("_", " ")
    .replace(
      /^\w/,
      (letter) =>
        letter.toUpperCase()
    );
}


function renderValue(value) {
  if (
    value === null
    || value === undefined
  ) {
    return "—";
  }

  if (typeof value === "object") {
    return (
      <pre className="inspector-json">
        {JSON.stringify(
          value,
          null,
          2
        )}
      </pre>
    );
  }

  return String(value);
}


const RESEARCHABLE_KINDS =
  new Set([
    "hypothesis",
    "evidence_requirement",
    "missing_evidence",
  ]);


export default function NodeInspector({
  node,
  onResearch,
  researchRunning = false,
  researchError = null,
}) {
  if (!node) {
    return (
      <aside className="inspector">
        <div className="node-type">
          Inspector
        </div>

        <h2>
          Select a node or relationship
        </h2>

        <p className="muted">
          Inspect what was observed,
          calculated, assumed or inferred;
          why evidence relates to a
          hypothesis; and which model or
          tool produced it.
        </p>
      </aside>
    );
  }


  const isEdge =
    node.inspectorType === "edge";


  const title =
    node.label
    ?? (
      isEdge
        ? node.kind
        : "Graph item"
    );


  const identifier =
    isEdge
      ? node.edge_id
      : node.node_id;


  /*
   * Cytoscape exposes our node properties directly
   * through event.target.data().
   *
   * Older ClaimGraph fixtures sometimes also contain
   * a nested `data` object, so merge both forms.
   */
  const nestedDetails =
    (
      !isEdge
      && typeof node.data === "object"
      && node.data !== null
    )
      ? node.data
      : {};


  const topLevelDetails =
    Object.fromEntries(
      Object.entries(node).filter(
        ([key]) =>
          ![
            "id",
            "node_id",
            "edge_id",
            "label",
            "kind",
            "data",
            "inspectorType",
            "displayKind",
          ].includes(key)
      )
    );


  const details =
    isEdge
      ? topLevelDetails
      : {
          ...nestedDetails,
          ...topLevelDetails,
        };


  const canResearch =
    (
      !isEdge
      && RESEARCHABLE_KINDS.has(
        node.kind
      )
      && Boolean(node.node_id)
      && Boolean(node.label)
      && Boolean(onResearch)
    );


  return (
    <aside className="inspector">

      <div className="node-type">
        {node.displayKind
          ?? (
            isEdge
              ? "Relationship"
              : node.kind
          )}
      </div>


      <h2>
        {title}
      </h2>


      <div className="inspector-row">
        <span>
          {isEdge
            ? "Edge ID"
            : "Node ID"}
        </span>

        <strong>
          {identifier}
        </strong>
      </div>


      {Object.entries(
        details
      ).map(([key, value]) => (
        <div
          className="inspector-row"
          key={key}
        >
          <span>
            {formatKey(key)}
          </span>

          {key === "url" ? (
            <a
              href={String(value)}
              target="_blank"
              rel="noreferrer"
            >
              Open source
            </a>
          ) : (
            <strong>
              {renderValue(value)}
            </strong>
          )}
        </div>
      ))}


      {canResearch && (
        <div className="research-control">

          <button
            type="button"
            className="research-node-button"

            disabled={
              researchRunning
            }

            onClick={() => {
              onResearch(node);
            }}
          >
            {researchRunning
              ? "RESEARCHING…"
              : "RESEARCH THIS NODE"}
          </button>

          <p className="research-help">
            Search for material that can
            support, contradict or contextualize
            this node.
          </p>

        </div>
      )}


      {researchError && (
        <div className="research-error">
          {researchError}
        </div>
      )}

    </aside>
  );
}
