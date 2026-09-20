import { nodeData, evidenceRoles } from './reviewModel.js';

const dependencies = ['extracted_from', 'sourced_from', 'calculated_from', 'derived_from'];
const contextKinds = ['agent_action', 'research_task', 'tool_call', 'anomaly', 'hypothesis', 'assumption', 'missing_evidence', 'evidence_requirement', 'model_run'];
const available = status => ['available_at_cutoff', 'derived_from_available_evidence'].includes(status);
// Require an explicit timezone. Never interpret retrieval or event time as publication.
const instant = value => typeof value === 'string' && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value)) ? Date.parse(value) : null;
export function originalCutoff(graph) {
  const data = nodeData(graph.nodes.find(n => n.kind === 'anomaly'));
  return data.observed_at ?? data.metadata?.observed_at ?? data.detected_at ?? null;
}
export function publicationBound(node) {
  const data = nodeData(node);
  if (!data.published_at) return null;
  if (data.published_date_only || /^\d{4}-\d{2}-\d{2}$/.test(data.published_at)) {
    // Conservative: a calendar date becomes eligible at the end of that entire day.
    const start = instant(`${data.published_at.slice(0,10)}T00:00:00Z`);
    return start === null ? null : start + 86399999;
  }
  return instant(data.published_at);
}
export function temporalStatuses(graph, cutoff) {
  const limit = cutoff === 'latest' ? Infinity : instant(cutoff);
  const byId = new Map(graph.nodes.map(n => [n.node_id,n]));
  const result = new Map();
  function visit(id, path = new Set()) {
    if (result.has(id)) return result.get(id);
    if (path.has(id) || !byId.has(id)) return 'date_unknown';
    const node = byId.get(id), data = nodeData(node);
    let status;
    if (data.temporal_role === 'hindsight_outcome' || data.hindsight_only === true) status = 'hindsight_outcome';
    else if (contextKinds.includes(node.kind) || (node.kind === 'context' && data.subtype === 'fundamentals')) status = 'investigation_context';
    else {
      const bound = publicationBound(node);
      const inputs = graph.edges.filter(e => e.source === id && dependencies.includes(e.kind)).map(e => e.target);
      const states = inputs.map(input => visit(input, new Set([...path,id])));
      if (bound !== null && limit !== null && bound > limit) status = 'appeared_after_cutoff';
      else if (states.some(s => s === 'appeared_after_cutoff' || s === 'hindsight_outcome')) status = 'appeared_after_cutoff';
      else if (inputs.length) status = states.every(available) && limit !== null ? 'derived_from_available_evidence' : 'date_unknown';
      else status = bound !== null && limit !== null && !['calculation','inference'].includes(node.kind) ? 'available_at_cutoff' : 'date_unknown';
    }
    result.set(id,status); return status;
  }
  graph.nodes.forEach(n => visit(n.node_id));
  return result;
}
export function temporalView(graph, cutoff) {
  const statuses = temporalStatuses(graph, cutoff);
  const nodes = graph.nodes.filter(n => {
    const status = statuses.get(n.node_id);
    return status === 'investigation_context' || available(status) || (cutoff === 'latest' && status !== 'hindsight_outcome');
  });
  // Publisher identities are context, never dated evidence; show only for visible documents.
  const ids = new Set(nodes.map(n => n.node_id));
  graph.edges.filter(e => e.kind === 'published_by' && ids.has(e.source)).forEach(e => ids.add(e.target));
  return {...graph, temporalStatuses:statuses, nodes:graph.nodes.filter(n => ids.has(n.node_id)), edges:graph.edges.filter(e => {
    if (!ids.has(e.source) || !ids.has(e.target)) return false;
    if (['supports','contradicts','weakens'].includes(e.kind)) return available(statuses.get(e.source));
    if (['supported_by','contradicted_by'].includes(e.kind)) return available(statuses.get(e.target));
    return true;
  })};
}
export function timelineSteps(graph) {
  const original = originalCutoff(graph);
  const dates = [...new Set(graph.nodes.map(publicationBound).filter(t => t !== null && t > (instant(original) ?? Infinity)))].sort((a,b) => a-b);
  return [{value:original ?? '', label:'At anomaly'}, ...dates.map(t => ({value:new Date(t).toISOString(),label:new Date(t).toISOString().replace('.000Z','Z')})), {value:'latest',label:'Hindsight / latest'}];
}
export function temporalSummary(graph, cutoff) {
  const view = temporalView(graph, cutoff);
  const statuses = temporalStatuses(graph, cutoff);
  const evidence = view.nodes.filter(n => available(statuses.get(n.node_id)));
  const ids = new Set(evidence.map(n => n.node_id));
  const roles = evidenceRoles(view);
  return {evidence:evidence.length, support:[...roles.support].filter(id => ids.has(id)).length,
    counter:[...roles.counter].filter(id => ids.has(id)).length,
    gaps:view.nodes.filter(n => n.kind === 'missing_evidence').length};
}
