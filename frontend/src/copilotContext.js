import { temporalView } from './temporalModel.js';

const clip = (value, max = 300) => String(value ?? '').slice(0, max);
const fields = ['value','unit','expression','input_observation_ids','input_calculation_ids','model_run_id','temporal_status','formula','method','description','published_at','published_date_only','retrieved_at','observed_at','document_id','source_id','resolution_status','period_start','period_end'];
function compact(node) {
  return {id:clip(node.node_id ?? node.edge_id, 200), kind:clip(node.kind, 80), label:clip(node.label),
    data:Object.fromEntries(fields.filter(k => node.data?.[k] != null).map(k => [k,clip(typeof node.data[k] === 'object' ? JSON.stringify(node.data[k]) : node.data[k], 250)]))};
}
export function buildCopilotViewContext({graph, workspaceId, model, selected, cutoff, filters = [], onlyNew = false}) {
  const visible = temporalView(graph, cutoff);
  const project = node => ({...compact(node), data:{...compact(node).data, temporal_status:visible.temporalStatuses.get(node.node_id) ?? 'relationship'}});
  const selectedNode = graph.nodes.find(n => n.node_id === selected?.node_id && visible.temporalStatuses.get(n.node_id) !== 'hindsight_outcome');
  const edges = visible.edges.filter(e => e.source === selectedNode?.node_id || e.target === selectedNode?.node_id);
  const related = edges.map(e => visible.nodes.find(n => n.node_id === (e.source === selectedNode?.node_id ? e.target : e.source))).filter(Boolean);
  const chosen = [...new Map([selectedNode, ...related, ...visible.nodes.filter(n => ['hypothesis','missing_evidence','evidence_requirement'].includes(n.kind))].filter(Boolean).map(n => [n.node_id,n])).values()].slice(0, 20);
  const counts = {};
  visible.nodes.forEach(n => {const kind = clip(n.kind,80); if (Object.keys(counts).length < 50 || Object.hasOwn(counts,kind)) counts[kind] = (counts[kind] ?? 0) + 1;});
  const context = {workspace:{id:clip(workspaceId,200), type:'investigation', title:clip(graph.ticker), cutoff:clip(cutoff)},
    investigation:{id:clip(graph.investigation_id,200), replay_id:clip(graph.replay_id,200), analysis_model:clip(model?.label ?? model?.model)},
    selection:selectedNode ? project(selectedNode) : selected?.edge_id ? compact(selected) : null,
    graph_summary:{primary_claim:clip(visible.nodes.find(n => n.kind === 'claim')?.label), counts,
      hypotheses:visible.nodes.filter(n => n.kind === 'hypothesis').slice(0,8).map(n => ({id:clip(n.node_id,200),label:clip(n.label)})),
      supporting:visible.edges.filter(e => ['supports','supported_by'].includes(e.kind)).length,
      weakening:visible.edges.filter(e => ['weakens','contradicts','contradicted_by'].includes(e.kind)).length,
      missing_evidence:(counts.missing_evidence ?? 0) + (counts.evidence_requirement ?? 0)},
    neighbourhood:edges.slice(0,20).map(e => ({source:clip(e.source,200), target:clip(e.target,200), kind:clip(e.kind,80)})),
    view:{filters:filters.slice(0,20).map(f => clip(f)), temporal_cutoff:clip(cutoff), show_only_new:onlyNew}, nodes:chosen.map(project), truncated:chosen.length < visible.nodes.length};
  const oversized = () => new TextEncoder().encode(JSON.stringify(context)).length > 22000;
  for (const items of [context.nodes, context.neighbourhood, context.graph_summary.hypotheses]) {
    while (oversized() && items.length) {items.pop(); context.truncated = true;}
  }
  if (oversized()) {context.selection = null; context.graph_summary.counts = {}; context.truncated = true;}
  return context;
}

export function applyCopilotAction(action, graph, handlers) {
  if (!action || action.type === 'none') return;
  const node = graph.nodes.find(n => n.node_id === action.node_id);
  switch (action.type) {
    case 'select_node': case 'open_provenance':
      if (!node) throw new Error('Unknown graph node');
      handlers.select(node); break;
    case 'show_supporting': handlers.filters(['support']); break;
    case 'show_counter': handlers.filters(['counter']); break;
    case 'show_kind':
      if (!graph.nodes.some(n => n.kind === action.kind)) throw new Error('Unknown graph kind');
      handlers.filters([action.kind]); break;
    case 'clear_filters': handlers.filters([]); break;
    case 'fit_graph': handlers.fit(); break;
    default: throw new Error('Unknown Copilot action');
  }
}
