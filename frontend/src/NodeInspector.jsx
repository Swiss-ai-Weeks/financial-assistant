function formatKey(key) {
  return key
    .replaceAll("_", " ")
    .replace(
      /^\w/,
      (letter) => letter.toUpperCase()
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
          Select a graph node
        </h2>

        <p className="muted">
          Inspect what was observed,
          reported, calculated or inferred,
          and where it came from.
        </p>
      </aside>
    );
  }

  return (
    <aside className="inspector">
      <div className="node-type">
        {node.displayKind ?? node.kind}
      </div>

      <h2>
        {node.label}
      </h2>

      <div className="inspector-row">
        <span>Node ID</span>
        <strong>{node.node_id}</strong>
      </div>

      {Object.entries(
        node.data ?? {}
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
