import { buildInvestigationReport, institutionalSections, reportExport, formatReportMetric } from "../../lib/claimgraph/investigationReport.js";
import tokens from "../../styles/tokens.css?raw";
import base from "../../styles/base.css?raw";
import workspace from "../../styles/workspace.css?raw";

function download(report, format) {
  const file = reportExport(report, format, `${tokens}\n${base}\n${workspace}`);
  const url = URL.createObjectURL(new Blob([file.text], { type: file.type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `pythia-${report.investigation_id.replace(/[^\w-]/g, "_")}.${file.extension}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ReportPanel({ graph, cutoff, workspaceId, onClose, onSelect, reportMode = "existing_position", onReportModeChange }) {
  let report;
  try {
    report = buildInvestigationReport(graph, { cutoff, workspaceId, reportMode });
  } catch (error) {
    return <div className="report"><button className="btn btn--ghost btn--small" onClick={onClose}>← Back to the graph</button><div className="error-banner">{error.message}</div></div>;
  }
  const references = (ids) => [...new Set(ids.filter(Boolean))].map(id => <button key={id} className="link-button mono" onClick={() => {
    const node = graph.nodes.find(n => n.node_id === id);
    if (node) { onClose(); onSelect(node); }
  }}>{id}</button>);
  const itemView = (item, index) => <article key={`${item.node_id ?? 'summary'}-${index}`} className="report__item">
    {item.kind && <span className="eyebrow">{item.kind.replaceAll('_', ' ')}{item.data?.status ? ` · ${item.data.status}` : ''}</span>}
    <p>{item.statement}</p>
    {item.related_claim && <p className="muted">Related claim: {item.related_claim}</p>}
    {item.rationale && <p>Recorded rationale: {item.rationale}</p>}
    {item.strength !== null && item.strength !== undefined && <small>Recorded relation strength: {item.strength}</small>}
    {references([item.node_id,...(item.node_ids ?? []),...(item.claim_ids ?? []),...(item.evidence_ids ?? []),...(item.counter_ids ?? []),...(item.source_node_ids ?? [])])}
    {item.kind && <small className="muted">{item.edge_id ? `${item.edge_id} · ` : ''}{item.source_node_ids?.length ? 'Linked source references above' : 'Source unavailable'}{item.temporal_status ? ` · ${item.temporal_status.replaceAll('_',' ')}` : ''}</small>}
    {item.kind && <details><summary className="muted">Recorded details / provenance</summary><pre className="inspector-json">{JSON.stringify(item.data,null,2)}</pre></details>}
  </article>;
  return <div className="report">
    <div className="report__actions">
      <button className="btn btn--ghost btn--small" onClick={onClose}>← Back to the graph</button>
      <label className="muted">Report context <select value={reportMode} onChange={e => onReportModeChange(e.target.value)}><option value="existing_position">Existing position</option><option value="new_position">New position</option></select></label>
      <button className="btn btn--small" onClick={() => download(report,"html")}>HTML / PDF</button>
      <button className="btn btn--ghost btn--small" onClick={() => download(report,"markdown")}>Markdown</button>
      <button className="btn btn--ghost btn--small" onClick={() => download(report,"json")}>JSON</button>
    </div>
    <header className="report__header">
      <span className="eyebrow">Pythia · ClaimGraph</span><h1>Investment Investigation Report</h1>
      <div className="report__metadata"><strong>{report.security}</strong><span>{reportMode === 'existing_position' ? 'Existing position' : 'New position'}</span><span className="mono">Evidence as of {report.cutoff}</span></div>
      <p>{report.question}</p><small className="muted mono">{report.investigation_id}</small>
      <p className="report__assessment">{report.overall_assessment}</p>
    </header>
    <section><h2>Executive summary</h2>{report.executive_summary.map(itemView)}</section>
    <section><h2>Evidence balance</h2><div className="report__balance">{Object.entries(report.evidence_balance).map(([key,count]) => <div key={key}><strong className="mono">{count}</strong><span className="eyebrow">{key}</span></div>)}</div>
      <div className="report__bar" aria-hidden="true">{Object.entries(report.evidence_balance).map(([key,count]) => count > 0 && <span key={key} className={`report__bar--${key}`} style={{flex:count}} />)}</div>
      <p className="muted">Unique nodes per category; a node may support one claim and oppose another. Unresolved includes recorded assumptions requiring validation. Counts do not measure evidence quality.</p>
    </section>
    {institutionalSections(report).map(section => <section key={section.key} className={section.key === 'counter_evidence' ? 'report__counter' : ''}><h2>{section.title}</h2>{section.items.length ? section.items.map(itemView) : <p className="muted">{section.empty}</p>}</section>)}
    {reportMode === 'new_position' && <section><h2>Portfolio simulation</h2>{!report.portfolio_simulation.length && <p className="muted">Portfolio simulation not available for this investigation.</p>}{report.portfolio_simulation.map(sim => <article key={sim.node_id} className="report__item">
      <h3>{sim.statement}</h3><p>{sim.data.construction}</p>
      <p className="muted mono">{sim.data.current.start} → {sim.data.current.end} · {sim.data.current.sessions} common sessions</p>
      <div className="report__table"><table className="table"><thead><tr><th>Metric</th><th>Current portfolio</th><th>With overlay</th><th>Change</th></tr></thead><tbody>{sim.rows.map(row => <tr key={row.label}><td>{row.label}</td><td className="mono">{formatReportMetric(row.current)}</td><td className="mono">{formatReportMetric(row.simulated)}</td><td className="mono">{formatReportMetric(row.change,true)}</td></tr>)}</tbody></table></div>
      {Number.isFinite(sim.data.gross_overlay) && <p>Gross overlay: {formatReportMetric(sim.data.gross_overlay)}</p>}
      {sim.data.correlation?.status === 'available' && Number.isFinite(sim.data.correlation.value) && <p>Candidate / book correlation: {sim.data.correlation.value.toFixed(3)}</p>}
      <p>{sim.data.interpretation}</p><p>{sim.data.remaining_question}</p>
      {references([sim.node_id,...sim.input_ids])}<details><summary>Calculation provenance</summary><pre className="inspector-json">{JSON.stringify(sim.data,null,2)}</pre></details>
    </article>)}</section>}
    <details><summary>Analytical appendix · observations, calculations, inferences and execution</summary>{['observations','calculations','inferences','confounders','execution'].map(key => <section key={key}><h2>{key}</h2>{report.sections[key].map(itemView)}</section>)}</details>
    <details><summary>{report.exclusions.length} items excluded by the cutoff</summary><pre className="inspector-json">{JSON.stringify(report.exclusions,null,2)}</pre></details>
    <p className="muted">{report.methodology.assembly}. {report.methodology.membership_basis} Thesis components are selected by linked supporting evidence count, not a materiality or quality ranking; no investment recommendation is inferred.</p>
  </div>;
}
