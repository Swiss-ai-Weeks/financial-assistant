import {originalCutoff, temporalView, temporalStatuses} from './temporalModel.js';

export const REPORT_SECTIONS = {
  key_claims:'Key claims / hypotheses', supporting_evidence:'Supporting evidence', counterpoints:'Counterpoints',
  observations:'Observations', calculations:'Metrics / calculations', inferences:'Inferences',
  assumptions:'Assumptions', confounders:'Confounders / context', unresolved:'Unresolved questions',
  sources:'Source appendix · epistemic provenance', execution:'Methodology / execution provenance',
};
const executionKinds = ['model_run','agent_action','tool_call','research_task'];
const lineageKinds = ['extracted_from','published_by','calculated_from','derived_from','sourced_from'];
export function buildInvestigationReport(graph, {cutoff=originalCutoff(graph), workspaceId=null, reportMode='existing_position'}={}) {
  if (!graph?.investigation_id || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new Error('A canonical investigation graph is required');
  if (!cutoff || cutoff === 'latest' || !Number.isFinite(Date.parse(cutoff))) throw new Error('Select an explicit evidence cutoff before preparing a report');
  if (!['existing_position', 'new_position'].includes(reportMode)) throw new Error('Unknown report mode');
  const visible = temporalView(graph, cutoff), statuses = temporalStatuses(graph, cutoff);
  const byId = new Map(visible.nodes.map(n => [n.node_id,n]));
  function lineage(id, visited=new Set()) {
    if (visited.has(id)) return visited;
    visited.add(id);
    visible.edges.filter(e => e.source === id && lineageKinds.includes(e.kind)).forEach(e => lineage(e.target, visited));
    return visited;
  }
  const item = n => {
    const ids = [...lineage(n.node_id)];
    return {node_id:n.node_id, kind:n.kind, statement:n.label, data:structuredClone(n.data ?? {}),
      temporal_status:statuses.get(n.node_id),
      edge_ids:visible.edges.filter(e => e.source === n.node_id || e.target === n.node_id).map(e => e.edge_id),
      source_node_ids:ids.filter(id => ['document','source'].includes(byId.get(id)?.kind)),
      lineage_node_ids:ids};
  };
  const sections = Object.fromEntries(Object.keys(REPORT_SECTIONS).map(k => [k,[]]));
  const categories = {primary_claim:'key_claims',subclaim:'key_claims',claim:'key_claims',hypothesis:'key_claims',observation:'observations',calculation:'calculations',
    inference:'inferences',assumption:'assumptions',context:'confounders',missing_evidence:'unresolved',evidence_requirement:'unresolved',document:'sources',source:'sources'};
  visible.nodes.forEach(n => {
    const section = executionKinds.includes(n.kind) ? 'execution' : categories[n.kind];
    if (section && (section !== 'unresolved' || n.data?.resolution_status !== 'answered' && n.data?.status !== 'satisfied')) sections[section].push(item(n));
  });
  for (const edge of visible.edges) {
    const section = ['supports','supported_by'].includes(edge.kind) ? 'supporting_evidence' : ['weakens','contradicts','contradicted_by'].includes(edge.kind) ? 'counterpoints' : null;
    if (section) sections[section].push({edge_id:edge.edge_id, kind:edge.kind, source:edge.source, target:edge.target,
      statement:`${byId.get(edge.source)?.label ?? edge.source} — ${edge.kind} → ${byId.get(edge.target)?.label ?? edge.target}`,
      node_ids:[edge.source,edge.target], source_node_ids:[...new Set([...lineage(edge.source),...lineage(edge.target)])].filter(id => ['source','document'].includes(byId.get(id)?.kind)), data:structuredClone(edge.data ?? {})});
  }
  const event = visible.nodes.find(n => n.kind === 'anomaly');
  const question = event?.data?.metadata?.question ?? event?.data?.question ?? event?.label ?? graph.ticker;
  const institutional = institutionalReport(visible, sections, item, reportMode);
  return {schema_version:'investigation-report-v2', ...institutional, investigation_id:graph.investigation_id,
    workspace_id:workspaceId, title:`${graph.ticker} · Investigation report`, security:graph.ticker,
    question, question_node_id:event?.node_id ?? null, cutoff, original_cutoff:originalCutoff(graph),
    interpretation:{statement:'Canonical analytical findings; hypotheses and inferences remain qualified by their evidence and unresolved requirements. No additional model synthesis.',
      node_ids:sections.inferences.map(n => n.node_id),
      items:(sections.inferences.length ? sections.inferences : sections.key_claims.filter(n => n.kind === 'hypothesis')).slice(0,3)},
    provenance:visible.nodes.map(item),
    sections, exclusions:graph.nodes.filter(n => !visible.nodes.some(v => v.node_id === n.node_id)).map(n => ({node_id:n.node_id,kind:n.kind,reason:statuses.get(n.node_id)})),
    methodology:{assembly:'Deterministic graph projection; no LLM or Copilot commentary',
      membership_basis:'Current snapshots only; historical constituent membership is not established.',
      graph_schema_version:graph.schema_version, followup_ids:(graph.followups ?? []).map(f => f.run_id)},
    // Complete lineage for traceability, kept separate from the admitted report sections.
    graph_snapshot:structuredClone(graph)};
}
// Institutional synthesis remains extractive: relation counts never imply investment quality.
function institutionalReport(graph, sections, item, reportMode) {
  const byId = new Map(graph.nodes.map(n => [n.node_id, n]));
  const relations = (kinds) => graph.edges.filter(e => kinds.includes(e.kind)).map(e => {
    const inverse = ['supported_by', 'contradicted_by'].includes(e.kind);
    const evidence = byId.get(inverse ? e.target : e.source);
    const claim = byId.get(inverse ? e.source : e.target);
    return {...item(evidence), edge_id:e.edge_id, relation:e.kind,
      claim_ids:[claim.node_id], related_claim:claim.label,
      rationale:e.data?.rationale ?? null, strength:e.data?.strength ?? null};
  }).sort((a,b) => (Number.isFinite(b.strength) ? b.strength : -1) - (Number.isFinite(a.strength) ? a.strength : -1));
  const unique = items => [...new Map(items.map(n => [n.node_id, n])).values()];
  const support = relations(['supports','supported_by']);
  const counter = relations(['weakens','contradicts','contradicted_by']);
  for (const n of graph.nodes) {
    if (n.kind === 'evidence' && !support.some(e => e.node_id === n.node_id)) support.push({...item(n),claim_ids:[]});
    if (n.kind === 'counter_evidence' && !counter.some(e => e.node_id === n.node_id)) counter.push({...item(n),claim_ids:[]});
  }
  const thesis = sections.key_claims.map(n => ({...n,
    evidence_ids:unique(support.filter(e => e.claim_ids.includes(n.node_id))).map(e => e.node_id),
    counter_ids:unique(counter.filter(e => e.claim_ids.includes(n.node_id))).map(e => e.node_id),
  })).sort((a,b) => b.evidence_ids.length - a.evidence_ids.length).slice(0,3);
  const gaps = unique([...sections.unresolved,
    ...sections.inferences.filter(n => ['weak','low','unresolved'].includes(n.data.status ?? n.data.confidence)),
    ...sections.assumptions.filter(n => !['validated','satisfied'].includes(n.data.status))]);
  const simulations = sections.calculations.filter(n => n.data.status === 'available' && n.data.current && n.data.combined && n.data.formula)
    .map(n => ({...n, input_ids:graph.edges.filter(e => e.source === n.node_id && e.kind === 'calculated_from').map(e => e.target),
      rows:[['return_window','Historical return'],['volatility','Annualised volatility'],['max_drawdown','Max drawdown']].map(([key,label]) => {
        const value = m => m?.status === 'available' && Number.isFinite(m.value) ? m.value : null;
        const current = value(n.data.current[key]), simulated = value(n.data.combined[key]);
        return {label,current,simulated,change:current !== null && simulated !== null ? simulated-current : null};
      })}));
  const counts = {supporting:unique(support).length, counter:unique(counter).length, unresolved:gaps.length};
  // These labels describe captured relations, never an inferred recommendation.
  const assessment = counts.supporting ? (counts.counter || counts.unresolved ? 'MIXED EVIDENCE' : 'SUPPORT RECORDED')
    : counts.counter ? 'COUNTER-EVIDENCE RECORDED' : 'UNRESOLVED';
  const executive = [
    {statement:`${reportMode === 'existing_position' ? 'Retention' : 'Initiation'} review: ${assessment.toLowerCase()}. Evidence quality requires review of the recorded sources and relation strengths; counts are not a confidence score.`,node_ids:[]},
    ...(thesis[0] ? [{statement:`Principal recorded thesis (${thesis[0].kind}): ${thesis[0].statement}`,node_ids:[thesis[0].node_id,...thesis[0].evidence_ids]}] : [{statement:'Evidence gap: no explicit investment thesis recorded.',node_ids:[]}]),
    ...(counter[0] ? [{statement:`Counterpoint: ${counter[0].statement}`,node_ids:[counter[0].node_id,...counter[0].claim_ids]}] : [{statement:'No material counter-evidence was captured in this investigation; this does not establish its absence.',node_ids:[]}]),
    ...(sections.assumptions[0] ? [{statement:`Recorded assumption: ${sections.assumptions[0].statement}`,node_ids:[sections.assumptions[0].node_id]}] : [{statement:'Evidence gap: no explicit assumption recorded.',node_ids:[]}]),
    ...(gaps[0] ? [{statement:`Requires validation: ${gaps[0].statement}`,node_ids:[gaps[0].node_id]}] : [{statement:'No unresolved question is explicitly recorded; completeness has not been established.',node_ids:[]}]),
    ...(reportMode === 'new_position' ? [{statement:simulations.length ? 'Recorded historical portfolio scenarios are shown below; they do not forecast future portfolio effects.' : 'Portfolio simulation not available for this investigation.',node_ids:simulations.map(n => n.node_id)}] : []),
  ];
  return {report_mode:reportMode, overall_assessment:assessment, executive_summary:executive,
    thesis, supporting_evidence:support, counter_evidence:counter, assumptions:sections.assumptions,
    risk_factors:counter, evidence_gaps:gaps, evidence_balance:counts,
    portfolio_simulation:reportMode === 'new_position' ? simulations : []};
}

export function institutionalSections(report) {
  const held = report.report_mode === 'existing_position';
  return [
    {key:'thesis',title:held ? 'Investment thesis · retaining the position' : 'Proposed investment thesis',items:report.thesis,empty:'Evidence gap: no explicit investment thesis recorded.'},
    {key:'counter_evidence',title:held ? 'Risk factors / counter-evidence' : 'Counter-evidence',items:report.counter_evidence,empty:'No material counter-evidence was captured in this investigation.'},
    {key:'supporting_evidence',title:held ? 'Evidence supporting the position' : 'Supporting evidence',items:report.supporting_evidence,empty:'No supporting evidence eligible at this cutoff.'},
    {key:'assumptions',title:held ? 'Key assumptions' : 'Critical assumptions',items:report.assumptions,empty:'Evidence gap: no explicit assumption recorded.'},
    {key:'evidence_gaps',title:held ? 'Evidence gaps / what would change the view' : 'Evidence gaps / what must be validated',items:report.evidence_gaps,empty:'No explicit unresolved questions recorded; completeness has not been established.'},
    {key:'sources',title:'Sources / provenance',items:report.sections.sources,empty:'Source unavailable'},
  ];
}
export const formatReportMetric = (value, change=false) => value === null ? '—' : `${(value*100).toFixed(2)}${change ? ' pp' : '%'}`;
const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const refs = item => [item.node_id,item.edge_id,...(item.node_ids ?? []),...(item.claim_ids ?? []),...(item.evidence_ids ?? []),...(item.counter_ids ?? []),...(item.source_node_ids ?? []),...(item.edge_ids ?? [])].filter(Boolean).join(', ');
export function reportMarkdown(report) {
  const lines = [`# ${report.title}`, `Context: ${report.report_mode}`, `Evidence cutoff: ${report.cutoff}`,
    `Investigation: ${report.investigation_id}`, `Question: ${report.question}`, `Assessment: ${report.overall_assessment}`, '', '## Executive summary',
    ...report.executive_summary.map(n => `- ${n.statement} [${(n.node_ids ?? []).join(', ')}]`),
    '', '## Evidence balance', JSON.stringify(report.evidence_balance)];
  for (const section of institutionalSections(report)) {
    lines.push('', `## ${section.title}`);
    if (!section.items.length) lines.push(section.empty);
    for (const n of section.items) lines.push(`- **${n.kind}**: ${n.statement} [${refs(n)}]`,
      n.related_claim ? `  Related claim: ${n.related_claim}` : '', n.rationale ? `  Recorded rationale: ${n.rationale}` : '',
      `  Sources: ${n.source_node_ids?.join(', ') || 'Source unavailable'}`);
  }
  if (report.report_mode === 'new_position') {
    lines.push('', '## Portfolio simulation');
    if (!report.portfolio_simulation.length) lines.push('Portfolio simulation not available for this investigation.');
    for (const sim of report.portfolio_simulation) lines.push(sim.statement, sim.data.construction,
      '| Metric | Current | With overlay | Change |', '| --- | --- | --- | --- |',
      ...sim.rows.map(r => `| ${r.label} | ${formatReportMetric(r.current)} | ${formatReportMetric(r.simulated)} | ${formatReportMetric(r.change,true)} |`),
      sim.data.interpretation, `References: ${sim.node_id}, ${sim.input_ids.join(', ')}`, `Calculation: ${JSON.stringify(sim.data)}`);
  }
  lines.push('', '## Analytical appendix');
  for (const key of ['observations','calculations','inferences','confounders','execution']) {
    lines.push(`### ${REPORT_SECTIONS[key]}`, ...report.sections[key].map(n => `- ${n.statement} [${refs(n)}]`));
  }
  lines.push('', '## Temporal exclusions', ...report.exclusions.map(n => `- ${n.node_id}: ${n.reason}`), '', report.methodology.assembly, report.methodology.membership_basis);
  return lines.filter(v => v !== undefined).join('\n');
}
export function reportHTML(report, styles='') {
  const e = escapeHTML;
  const refLinks = ids => [...new Set(ids.filter(Boolean))].map(id => `<a class="link-button mono" href="#${e(id)}">${e(id)}</a>`).join(' ');
  const renderItem = n => `<article class="report__item"><span class="eyebrow">${e(n.kind)}</span><p>${e(n.statement)}</p>${n.related_claim ? `<p>Related claim: ${e(n.related_claim)}</p>` : ''}${n.rationale ? `<p>Recorded rationale: ${e(n.rationale)}</p>` : ''}${n.strength != null ? `<small>Recorded relation strength: ${e(n.strength)}</small>` : ''}${refLinks([n.node_id,...(n.node_ids ?? []),...(n.claim_ids ?? []),...(n.evidence_ids ?? []),...(n.counter_ids ?? []),...(n.source_node_ids ?? [])])}${n.kind ? `<small>${e(n.source_node_ids?.length ? 'Linked sources above' : 'Source unavailable')}</small>` : ''}</article>`;
  const balance = Object.entries(report.evidence_balance);
  const simulation = report.report_mode !== 'new_position' ? '' : `<section><h2>Portfolio simulation</h2>${report.portfolio_simulation.length ? report.portfolio_simulation.map(sim => `<article class="report__item"><h3>${e(sim.statement)}</h3><p>${e(sim.data.construction)}</p><p>${e(sim.data.current.start)} → ${e(sim.data.current.end)} · ${e(sim.data.current.sessions)} common sessions</p><table><thead><tr><th>Metric</th><th>Current portfolio</th><th>With overlay</th><th>Change</th></tr></thead><tbody>${sim.rows.map(r => `<tr><td>${e(r.label)}</td><td>${formatReportMetric(r.current)}</td><td>${formatReportMetric(r.simulated)}</td><td>${formatReportMetric(r.change,true)}</td></tr>`).join('')}</tbody></table><p>${e(sim.data.interpretation)}</p><p>${e(sim.data.remaining_question)}</p>${refLinks([sim.node_id,...sim.input_ids])}</article>`).join('') : '<p>Portfolio simulation not available for this investigation.</p>'}</section>`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${e(report.title)}</title><style>${styles}</style><style>body{min-width:0;height:auto}.report{margin:24px auto}.report pre{white-space:pre-wrap;overflow-wrap:anywhere}@media print{.report .report__appendix{display:block}}</style></head><body><main class="report"><div class="report__actions"><button class="btn" onclick="window.print()">Print / Save as PDF</button></div><header class="report__header"><span class="eyebrow">PYTHIA · CLAIMGRAPH</span><h1>Investment Investigation Report</h1><p>${e(report.security)} · ${report.report_mode === 'existing_position' ? 'Existing position' : 'New position'}</p><p>${e(report.question)}</p><p>Evidence as of ${e(report.cutoff)} · ${e(report.investigation_id)}</p><p class="report__assessment">${e(report.overall_assessment)}</p></header><section><h2>Executive summary</h2>${report.executive_summary.map(renderItem).join('')}</section><section><h2>Evidence balance</h2><div class="report__balance">${balance.map(([key,count]) => `<div><strong>${count}</strong><span>${key}</span></div>`).join('')}</div><div class="report__bar">${balance.filter(([,count]) => count).map(([key,count]) => `<span class="report__bar--${key}" style="flex:${count}"></span>`).join('')}</div><p>Unique nodes per category; categories may overlap. Counts do not measure evidence quality.</p></section>${institutionalSections(report).map(section => `<section class="${section.key === 'counter_evidence' ? 'report__counter' : ''}"><h2>${e(section.title)}</h2>${section.items.map(renderItem).join('') || `<p>${e(section.empty)}</p>`}</section>`).join('')}${simulation}<section class="report__appendix"><h2>Recorded details / provenance</h2>${report.provenance.map(n => `<details id="${e(n.node_id)}"><summary>${e(n.node_id)} · ${e(n.kind)} · ${e(n.statement)}</summary><pre>${e(JSON.stringify(n.data,null,2))}</pre></details>`).join('')}</section><section><h2>Temporal exclusions</h2><p>${report.exclusions.length} nodes excluded.</p><pre>${e(JSON.stringify(report.exclusions,null,2))}</pre></section><p>${e(report.methodology.assembly)}. ${e(report.methodology.membership_basis)} Thesis selection uses linked support count, not a materiality ranking.</p></main></body></html>`;
}
export function reportExport(report, format, styles='') {
  if (format === 'json') return {text:JSON.stringify(report,null,2), type:'application/json',extension:'json'};
  if (format === 'html') return {text:reportHTML(report, styles),type:'text/html',extension:'html'};
  if (format === 'markdown') return {text:reportMarkdown(report),type:'text/markdown',extension:'md'};
  throw new Error('Unknown report format');
}
