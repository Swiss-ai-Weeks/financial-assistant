function Score({ value }) {
  if (value === null || value === undefined) {
    return null;
  }

  return (
    <div className="inspector-row">
      <span>Score</span>
      <strong>{Math.round(value * 100)}%</strong>
    </div>
  );
}


export default function NodeInspector({ node }) {
  if (!node) {
    return (
      <aside className="inspector">
        <h2>Inspect the reasoning</h2>

        <p className="muted">
          Select a claim, subclaim, evidence item,
          source, or alternative explanation.
        </p>
      </aside>
    );
  }

  return (
    <aside className="inspector">
      <div className="node-type">
        {node.kind.replaceAll("_", " ")}
      </div>

      <h2>{node.label}</h2>

      {node.assessment && (
        <div className="inspector-row">
          <span>Assessment</span>
          <strong>{node.assessment}</strong>
        </div>
      )}

      <Score value={node.score} />

      {node.criterion_name && (
        <div className="inspector-row">
          <span>Criterion</span>
          <strong>{node.criterion_name}</strong>
        </div>
      )}

      {node.method && (
        <div className="inspector-row">
          <span>Produced by</span>
          <strong>{node.method}</strong>
        </div>
      )}

      {node.rationale && (
        <section>
          <h3>Why?</h3>
          <p>{node.rationale}</p>
        </section>
      )}

      {node.evidence_ids?.length > 0 && (
        <section>
          <h3>Evidence</h3>

          <div className="evidence-tags">
            {node.evidence_ids.map((id) => (
              <span key={id} className="evidence-tag">
                {id}
              </span>
            ))}
          </div>
        </section>
      )}

      {node.source_name && (
        <section>
          <h3>Source</h3>

          <p>{node.source_name}</p>

          {node.source_uri && (
            <a
              href={node.source_uri}
              target="_blank"
              rel="noreferrer"
            >
              Open original source
            </a>
          )}
        </section>
      )}
    </aside>
  );
}