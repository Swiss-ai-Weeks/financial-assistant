import {buildInvestigationReport, REPORT_SECTIONS, reportExport} from './investigationReport.js';
export default function InvestigationReport({graph, cutoff, workspaceId, onClose, onSelect}) {
  let report;
  try { report = buildInvestigationReport(graph,{cutoff,workspaceId}); }
  catch (error) { return <section className="report-panel"><button onClick={onClose}>Back to graph</button><p role="alert">{error.message}</p></section>; }
  function download(format) {
    const file = reportExport(report,format), url = URL.createObjectURL(new Blob([file.text],{type:file.type}));
    const link = document.createElement('a'); link.href=url; link.download=`pythia-${graph.investigation_id.replace(/[^\w-]/g,'_')}.${file.extension}`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
  }
  return <section className="report-panel" aria-label="Investigation report"><div className="report-actions"><button onClick={onClose}>Back to graph</button><button onClick={() => download('html')}>Printable HTML / PDF</button><button onClick={() => download('markdown')}>Markdown</button><button onClick={() => download('json')}>JSON</button></div>
    <p className="eyebrow">PYTHIA / CLAIMGRAPH · INVESTMENT REVIEW</p><h1>{report.title}</h1><p>{report.question}</p><p>Evidence cutoff {report.cutoff} · {report.investigation_id}</p>
    <h2>Executive interpretation</h2><p>{report.interpretation.statement}</p>{report.interpretation.items.map(n => <article key={n.node_id}><span className="eyebrow">{n.kind}</span><p>{n.statement}</p><button onClick={() => {onClose();onSelect(graph.nodes.find(item => item.node_id === n.node_id));}}>{n.node_id}</button></article>)}<p>Download HTML, open it, then Print / Save as PDF.</p>
    {Object.entries(REPORT_SECTIONS).map(([key,title]) => <section key={key}><h2>{title}</h2>{report.sections[key].map((n,i) => <article key={n.node_id ?? n.edge_id ?? i}><span className="eyebrow">{n.kind}</span><p>{n.statement}</p>
      {[n.node_id,...(n.node_ids ?? [])].filter(Boolean).map(id => <button key={id} onClick={() => {onClose();onSelect(graph.nodes.find(n => n.node_id === id));}}>{id}</button>)}<small>{n.edge_id} · Sources: {n.source_node_ids.join(', ') || 'No linked source recorded'}</small><details><summary>Canonical details / lineage</summary><pre>{JSON.stringify(n,null,2)}</pre></details></article>)}{!report.sections[key].length && <p>None recorded / eligible at this cutoff.</p>}</section>)}
    <details><summary>{report.exclusions.length} temporal exclusions</summary><pre>{JSON.stringify(report.exclusions,null,2)}</pre></details><p>{report.methodology.membership_basis}</p>
  </section>;
}
