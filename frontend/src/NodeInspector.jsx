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
    value === null ||
    value === undefined
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


export default function NodeInspector({
  node,
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
          reported, assumed or inferred;
          why evidence relates to a
          hypothesis; and which model run
          produced it.
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

  const details = isEdge
    ? Object.fromEntries(
        Object.entries(node).filter(
          ([key]) =>
            ![
              "inspectorType",
              "displayKind",
              "label",
              "edge_id",
            ].includes(key)
        )
      )
    : (
        node.data
        ?? {}
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
    </aside>
  );
}
