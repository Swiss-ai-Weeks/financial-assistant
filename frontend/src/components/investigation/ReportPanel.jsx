import {
  REPORT_SECTIONS,
  buildInvestigationReport,
  reportExport,
} from "../../lib/claimgraph/investigationReport.js";

function download(report, graph, format) {
  const file = reportExport(report, format);
  const url = URL.createObjectURL(new Blob([file.text], { type: file.type }));

  const link = document.createElement("a");

  link.href = url;
  link.download = `pythia-${graph.investigation_id.replace(/[^\w-]/g, "_")}.${file.extension}`;
  link.click();

  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * The investigation as a document.
 *
 * A projection of the graph at an explicit cutoff, built
 * without a model: every sentence is a recorded node or
 * relation and keeps its id, so a reader can go from the
 * report straight back to the evidence.
 */
export default function ReportPanel({ graph, cutoff, workspaceId, onClose, onSelect }) {
  let report;

  try {
    report = buildInvestigationReport(graph, { cutoff, workspaceId });
  } catch (error) {
    return (
      <div className="report">
        <button className="btn btn--ghost btn--small" onClick={onClose}>
          ← Back to the graph
        </button>
        <div className="error-banner">{error.message}</div>
      </div>
    );
  }

  const open = (id) => {
    const node = graph.nodes.find((item) => item.node_id === id);

    if (node) {
      onClose();
      onSelect(node);
    }
  };

  return (
    <div className="report">
      <div className="report__actions">
        <button className="btn btn--ghost btn--small" onClick={onClose}>
          ← Back to the graph
        </button>
        <span className="muted">Open the HTML and print it to save a PDF.</span>
        <button className="btn btn--small" onClick={() => download(report, graph, "html")}>
          HTML / PDF
        </button>
        <button className="btn btn--ghost btn--small" onClick={() => download(report, graph, "markdown")}>
          Markdown
        </button>
        <button className="btn btn--ghost btn--small" onClick={() => download(report, graph, "json")}>
          JSON
        </button>
      </div>

      <span className="eyebrow">Pythia · ClaimGraph investment review</span>
      <h1>{report.title}</h1>
      <p>{report.question}</p>
      <p className="muted mono">
        evidence cutoff {report.cutoff} · {report.investigation_id}
      </p>

      <section>
        <h2>Executive interpretation</h2>
        <p>{report.interpretation.statement}</p>

        {report.interpretation.items.map((item) => (
          <article key={item.node_id} className="report__item">
            <span className="eyebrow">{item.kind}</span>
            <p>{item.statement}</p>
            <button className="link-button mono" onClick={() => open(item.node_id)}>
              {item.node_id}
            </button>
          </article>
        ))}
      </section>

      {Object.entries(REPORT_SECTIONS).map(([key, title]) => (
        <section key={key}>
          <h2>
            {title} <small className="muted mono">{report.sections[key].length}</small>
          </h2>

          {report.sections[key].length === 0 && (
            <p className="muted">None recorded or eligible at this cutoff.</p>
          )}

          {report.sections[key].map((item, index) => (
            <article key={item.node_id ?? item.edge_id ?? index} className="report__item">
              <span className="eyebrow">{item.kind}</span>
              <p>{item.statement}</p>

              {[item.node_id, ...(item.node_ids ?? [])].filter(Boolean).map((id) => (
                <button key={id} className="link-button mono" onClick={() => open(id)}>
                  {id}
                </button>
              ))}

              <small className="muted">
                {item.edge_id && `${item.edge_id} · `}
                sources: {item.source_node_ids?.join(", ") || "none linked"}
              </small>
            </article>
          ))}
        </section>
      ))}

      <details>
        <summary>{report.exclusions.length} items excluded by the cutoff</summary>
        <pre className="inspector-json">{JSON.stringify(report.exclusions, null, 2)}</pre>
      </details>

      <p className="muted">{report.methodology.membership_basis}</p>
    </div>
  );
}
