import {originalCutoff, temporalView, temporalStatuses} from './temporalModel.js';

export const REPORT_SECTIONS = {
  key_claims:'Key claims / hypotheses', supporting_evidence:'Supporting evidence', counterpoints:'Counterpoints',
  observations:'Observations', calculations:'Metrics / calculations', inferences:'Inferences',
  assumptions:'Assumptions', confounders:'Confounders / context', unresolved:'Unresolved questions',
  sources:'Source appendix · epistemic provenance', execution:'Methodology / execution provenance',
};
const executionKinds = ['model_run','agent_action','tool_call','research_task'];
const lineageKinds = ['extracted_from','published_by','calculated_from','derived_from','sourced_from'];
export function buildInvestigationReport(graph, {cutoff=originalCutoff(graph), workspaceId=null}={}) {
  if (!graph?.investigation_id || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new Error('A canonical investigation graph is required');
  if (!cutoff || cutoff === 'latest' || !Number.isFinite(Date.parse(cutoff))) throw new Error('Select an explicit evidence cutoff before preparing a report');
  const visible = temporalView(graph, cutoff), statuses = temporalStatuses(graph, cutoff);
  const byId = new Map(graph.nodes.map(n => [n.node_id,n]));
  function lineage(id, visited=new Set()) {
    if (visited.has(id)) return visited;
    visited.add(id);
    graph.edges.filter(e => e.source === id && lineageKinds.includes(e.kind)).forEach(e => lineage(e.target, visited));
    return visited;
  }
  const item = n => {
    const ids = [...lineage(n.node_id)];
    return {node_id:n.node_id, kind:n.kind, statement:n.label, data:structuredClone(n.data ?? {}),
      temporal_status:statuses.get(n.node_id),
      edge_ids:graph.edges.filter(e => e.source === n.node_id || e.target === n.node_id).map(e => e.edge_id),
      source_node_ids:ids.filter(id => ['document','source'].includes(byId.get(id)?.kind)),
      lineage_node_ids:ids};
  };
  const sections = Object.fromEntries(Object.keys(REPORT_SECTIONS).map(k => [k,[]]));
  const categories = {claim:'key_claims',hypothesis:'key_claims',observation:'observations',calculation:'calculations',
    inference:'inferences',assumption:'assumptions',context:'confounders',missing_evidence:'unresolved',evidence_requirement:'unresolved',document:'sources',source:'sources'};
  visible.nodes.forEach(n => {
    const section = executionKinds.includes(n.kind) ? 'execution' : categories[n.kind];
    if (section && (section !== 'unresolved' || n.data?.resolution_status !== 'answered')) sections[section].push(item(n));
  });
  for (const edge of visible.edges) {
    const section = ['supports','supported_by'].includes(edge.kind) ? 'supporting_evidence' : ['weakens','contradicts','contradicted_by'].includes(edge.kind) ? 'counterpoints' : null;
    if (section) sections[section].push({edge_id:edge.edge_id, kind:edge.kind, source:edge.source, target:edge.target,
      statement:`${byId.get(edge.source)?.label ?? edge.source} — ${edge.kind} → ${byId.get(edge.target)?.label ?? edge.target}`,
      node_ids:[edge.source,edge.target], source_node_ids:[...new Set([...lineage(edge.source),...lineage(edge.target)])].filter(id => ['source','document'].includes(byId.get(id)?.kind)), data:structuredClone(edge.data ?? {})});
  }
  const event = graph.nodes.find(n => n.kind === 'anomaly');
  const question = event?.data?.metadata?.question ?? event?.data?.question ?? event?.label ?? graph.ticker;
  return {schema_version:'investigation-report-v1', investigation_id:graph.investigation_id,
    workspace_id:workspaceId, title:`${graph.ticker} · Investigation report`, security:graph.ticker,
    question, question_node_id:event?.node_id ?? null, cutoff, original_cutoff:originalCutoff(graph),
    interpretation:{statement:'Canonical analytical findings; hypotheses and inferences remain qualified by their evidence and unresolved requirements. No additional model synthesis.',
      node_ids:sections.inferences.map(n => n.node_id),
      items:(sections.inferences.length ? sections.inferences : sections.key_claims.filter(n => n.kind === 'hypothesis')).slice(0,3)},
    sections, exclusions:graph.nodes.filter(n => !visible.nodes.some(v => v.node_id === n.node_id)).map(n => ({node_id:n.node_id,kind:n.kind,reason:statuses.get(n.node_id)})),
    methodology:{assembly:'Deterministic graph projection; no LLM or Copilot commentary',
      membership_basis:'Current snapshots only; historical constituent membership is not established.',
      graph_schema_version:graph.schema_version, followup_ids:(graph.followups ?? []).map(f => f.run_id)},
    // Complete lineage for traceability, kept separate from the admitted report sections.
    graph_snapshot:structuredClone(graph)};
}
const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const refs = item => [item.node_id,item.edge_id,...(item.node_ids ?? []),...(item.source_node_ids ?? []),...(item.edge_ids ?? [])].filter(Boolean).join(', ');
export function reportMarkdown(report) {
  const lines = [`# ${report.title}`, '', `Question: ${report.question} [${report.question_node_id ?? 'unrecorded'}]`,
    `Evidence cutoff: ${report.cutoff}`, `Investigation: ${report.investigation_id}`, '', '## Executive interpretation', report.interpretation.statement, ...report.interpretation.items.map(n => `- **${n.kind}**: ${n.statement} [${n.node_id}]`)];
  for (const [key,title] of Object.entries(REPORT_SECTIONS)) {
    lines.push('',`## ${title}`);
    for (const item of report.sections[key]) lines.push(`- **${item.kind}**: ${item.statement}\n  References: ${refs(item)}\n  Details: ${JSON.stringify(item.data)}`);
    if (!report.sections[key].length) lines.push('None recorded / eligible at this cutoff.');
  }
  lines.push('', '## Temporal exclusions', ...report.exclusions.map(n => `- ${n.node_id}: ${n.reason}`), '', report.methodology.membership_basis);
  return lines.join('\n');
}
export function reportHTML(report) {
  return `<!doctype html><html lang="en"><meta charset="utf-8"><title>${escapeHTML(report.title)}</title><style>body{font:15px/1.6 system-ui;max-width:960px;margin:40px auto;color:#171717;padding:20px}h1,h2{font-weight:500}article{break-inside:avoid;border-bottom:1px solid #ddd;padding:12px 0}small,pre{overflow-wrap:anywhere;white-space:pre-wrap}button{padding:10px}@media print{button{display:none}body{margin:0;max-width:none}h2{break-after:avoid}}</style><button onclick="window.print()">Print / Save as PDF</button><h1>PYTHIA · ${escapeHTML(report.title)}</h1><p>${escapeHTML(report.question)} [${escapeHTML(report.question_node_id)}]</p><p>Evidence cutoff: ${escapeHTML(report.cutoff)} · ${escapeHTML(report.investigation_id)}</p><h2>Executive interpretation</h2><p>${escapeHTML(report.interpretation.statement)}</p>${report.interpretation.items.map(n => `<article><strong>${escapeHTML(n.kind)}</strong><p>${escapeHTML(n.statement)}</p><small>${escapeHTML(refs(n))}</small></article>`).join('')}${Object.entries(REPORT_SECTIONS).map(([key,title]) => `<h2>${title}</h2>${report.sections[key].map(n => `<article><strong>${escapeHTML(n.kind)}</strong><p>${escapeHTML(n.statement)}</p><small>${escapeHTML(refs(n))}</small><pre>${escapeHTML(JSON.stringify(n.data,null,2))}</pre></article>`).join('') || '<p>None recorded / eligible at this cutoff.</p>'}`).join('')}<h2>Temporal exclusions</h2><pre>${escapeHTML(JSON.stringify(report.exclusions,null,2))}</pre><p>${escapeHTML(report.methodology.membership_basis)}</p></html>`;
}
export function reportExport(report, format) {
  if (format === 'json') return {text:JSON.stringify(report,null,2), type:'application/json',extension:'json'};
  if (format === 'html') return {text:reportHTML(report),type:'text/html',extension:'html'};
  if (format === 'markdown') return {text:reportMarkdown(report),type:'text/markdown',extension:'md'};
  throw new Error('Unknown report format');
}
