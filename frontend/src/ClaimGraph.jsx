import { temporalView, temporalStatuses } from './temporalModel.js';
import { useMemo, useState } from 'react';
import { Background, Controls, Handle, MiniMap, Position, ReactFlow, applyNodeChanges } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { quarterlyView, toReactFlowEdges, toReactFlowNodes } from './graphAdapter';
import { evidenceRoles, filterGraph, itemKey, labelFor } from './reviewModel.js';

function EvidenceNode({data}) {
  return <><Handle type="target" position={Position.Top} />
    <div className="graph-node-type">{data.displayKind}</div>
    <div className="graph-node-content">{data.label}</div>
    <div className="graph-node-tags"><span>{labelFor(data.temporalStatus)}</span>{data.support && <span className="support-tag">Supports</span>}{data.counter && <span className="counter-tag">Counters / weakens</span>}
      {data.humanState && <span>{labelFor(data.humanState)}</span>}</div>
    <Handle type="source" position={Position.Bottom} /></>;
}
const NODE_TYPES = { evidenceNode:EvidenceNode };

export default function ClaimGraph({graph, onSelectItem, itemReviews = {}, cutoff = 'latest'}) {
  const [showAtomic, setShowAtomic] = useState(false);
  const [showOlder, setShowOlder] = useState(false);
  const [expanded, setExpanded] = useState([]);
  const [filters, setFilters] = useState([]);
  const [flow, setFlow] = useState(null);
  const [layoutNodes, setLayoutNodes] = useState(() => toReactFlowNodes(graph.nodes));
  const roles = useMemo(() => evidenceRoles(temporalView(graph, cutoff)), [graph, cutoff]);
  const visible = filterGraph(quarterlyView(temporalView(graph, cutoff), { showAtomic, showOlder, expanded }), filters);
  const statuses = temporalStatuses(graph, cutoff);
  const ids = new Set(visible.nodes.map(n => n.node_id));
  const compactLayout = toReactFlowNodes(visible.nodes);
  const positions = new Map(compactLayout.map(n => [n.id, n.position]));
  const stored = new Map(layoutNodes.map(n => [n.id, n]));
  const mergedLayout = toReactFlowNodes(graph.nodes).map(n => {
    const prior = stored.get(n.id);
    return prior ? {...prior, data:{...n.data, dragged:prior.data.dragged}} : n;
  });
  const nodes = mergedLayout.map(n => ({...n, position: n.data.dragged || graph.followups?.length ? n.position : positions.get(n.id) ?? n.position, type:'evidenceNode', hidden:!ids.has(n.id),
    className:`${n.className}${roles.counter.has(n.id) ? ' cg-node--counter-role' : ''}`,
    data:{...n.data, temporalStatus:statuses.get(n.id), support:roles.support.has(n.id), counter:roles.counter.has(n.id), humanState:itemReviews[itemKey(n.data)]?.status}}));
  const edges = toReactFlowEdges(graph.edges).map(e => ({...e, hidden:!ids.has(e.source) || !ids.has(e.target)}));
  const kinds = [...new Set(graph.nodes.map(n => n.kind))];
  const options = [['support','Supporting evidence'],['counter','Counter-evidence'],...kinds.map(k => [k,k === 'model_run' ? 'Agent / model actions' : labelFor(k)])];
  return <>
    <div className="graph-filters" aria-label="Graph filters"><div className="filter-options"><button aria-pressed={!filters.length} onClick={() => setFilters([])}>All types</button>
      {options.map(([value,label]) => <button key={value} aria-pressed={filters.includes(value)} onClick={() => setFilters(current => current.includes(value) ? current.filter(f => f !== value) : [...current,value])}>{label}</button>)}
    </div><div className="graph-navigation"><button aria-pressed={showAtomic} onClick={() => setShowAtomic(v => !v)}>SEC atomic evidence</button><button aria-pressed={showOlder} onClick={() => setShowOlder(v => !v)}>Older quarters</button><button onClick={() => flow?.fitView({padding:0.15})}>Fit visible nodes</button>
      <label>Inspect / focus a visible item<select value="" onChange={e => {
        const node = nodes.find(n => n.id === e.target.value);
        if (node) { onSelectItem?.(node.data); flow?.fitView({nodes:[{id:node.id}],padding:0.8,maxZoom:1}); }
      }}><option value="">Choose an item…</option>{visible.nodes.map(n => <option key={n.node_id} value={n.node_id}>{labelFor(n.kind)} · {n.label}</option>)}</select></label></div>
    <p>{visible.nodes.length} / {graph.nodes.length} nodes visible · Filters combine selected types and roles. Only relationships between visible nodes are shown. Inspector retains the full graph.</p></div>
    {!visible.nodes.length && <p className="empty-state">No matching nodes recorded. Choose another filter or show all types.</p>}
    <div className="graph-container"><ReactFlow nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} onInit={setFlow}
      onNodesChange={changes => setLayoutNodes(current => applyNodeChanges(changes, [...current, ...mergedLayout.filter(n => !current.some(c => c.id === n.id))]).map(n => changes.some(c => c.id === n.id && c.type === 'position' && c.dragging) ? {...n, data:{...n.data, dragged:true}} : n))}
      fitView fitViewOptions={{padding:0.12}} minZoom={0.08} maxZoom={1.8}
      onNodeClick={(_,node) => {
        onSelectItem?.(node.data);
        if (node.data.data?.subtype === 'fundamental_snapshot') setExpanded(current => current.includes(node.id) ? current.filter(id => id !== node.id) : [...current, node.id]);
      }} onEdgeClick={(_,edge) => onSelectItem?.(edge.data)}>
      <Background /><Controls showInteractive={false} /><MiniMap pannable zoomable />
    </ReactFlow></div>
  </>;
}
