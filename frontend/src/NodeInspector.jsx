import { originalCutoff, temporalStatuses } from './temporalModel.js';
import { nodeData, provenanceFor, sourceCategory, labelFor } from './reviewModel.js';
import { ReviewActions } from './ReviewWorkspace';

function renderValue(value) {
  if (value === null || value === undefined) return 'Not recorded';
  if (typeof value === 'object') return <pre className="inspector-json">{JSON.stringify(value,null,2)}</pre>;
  return String(value);
}
function Details({data}) {
  return Object.entries(data).map(([key,value]) => <div className="inspector-row" key={key}>
    <span>{labelFor(key)}</span><div>{['url','source_uri'].includes(key) && /^https?:\/\//i.test(String(value))
      ? <a href={value} target="_blank" rel="noreferrer">Open source ↗</a> : renderValue(value)}</div>
  </div>);
}

export default function NodeInspector({node, graph, onSelect, onAction, reviewState, cutoff = 'latest'}) {
  if (!node) return <aside className="inspector"><div className="node-type">Inspector</div><h2>Select a node or relationship</h2>
    <p className="muted">Inspect observations, calculations, assumptions, and inferences. Follow sources and model runs, then record a human review.</p>
    <p className="muted">Evidence roles belong to relationships: one item can support one hypothesis and weaken another.</p></aside>;
  const isEdge = node.inspectorType === 'edge';
  const details = isEdge ? {...node.data, ...Object.fromEntries(Object.entries(node).filter(([key]) => !['data','inspectorType','displayKind','label','edge_id'].includes(key)))}
    : node.data ?? Object.fromEntries(Object.entries(node).filter(([key]) => !['node_id','kind','label','inspectorType','displayKind','support','counter','humanState'].includes(key)));
  const provenance = provenanceFor(graph,node);
  const selectId = id => {const target = graph.nodes.find(n => n.node_id === id); if (target) onSelect(target);};
  return <aside className="inspector">
    <div className="node-type">{isEdge ? 'Relationship' : labelFor(node.kind)}</div><h2>{node.label ?? labelFor(node.kind)}</h2>
    <section className="temporal-review"><h3>Temporal provenance — full recorded item</h3>
      <Details data={{inspection_cutoff:cutoff || 'Unavailable', temporal_status:isEdge ? 'Relationship endpoints must both be eligible' : temporalStatuses(graph, cutoff).get(node.node_id),
        published_at:details.published_date_only ? `${String(details.published_at).slice(0,10)} (date only; time unavailable)` : details.published_at ?? 'Unavailable',
        event_at:details.event_at ?? 'Unavailable', observed_at:details.observed_at ?? originalCutoff(graph) ?? 'Unavailable', retrieved_at:details.retrieved_at ?? 'Unavailable'}} />
      <p>Inspector retains future and hidden items for audit. Retrieval time never establishes publication time.</p>
    </section>
    <Details data={{[isEdge ? 'edge_id' : 'node_id']:node.edge_id ?? node.node_id}} />
    {!isEdge && ['source','document','calculation','inference'].includes(node.kind) && <Details data={{display_source_category:sourceCategory(node)}} />}
    {isEdge && <div className="relationship-endpoints"><button onClick={() => selectId(node.source)}>Inspect source node</button><span>{labelFor(node.kind)}</span><button onClick={() => selectId(node.target)}>Inspect target node</button></div>}
    {!isEdge && <section><h3>Epistemic relationships</h3>{provenance.relationships.length ? provenance.relationships.map(e => {
      const outgoing = e.source === node.node_id;
      const other = graph.nodes.find(n => n.node_id === (outgoing ? e.target : e.source));
      return <div className="relationship-row" key={e.edge_id}><button className="relation-button" onClick={() => onSelect({...e,inspectorType:'edge'})}>{outgoing ? '→' : '←'} {labelFor(e.kind)}</button>
        <button className="text-button" onClick={() => other && onSelect(other)}>{other?.label ?? 'Unresolved reference'}</button></div>;
    }) : <p className="muted">No relationships recorded.</p>}</section>}
    <section><h3>Source provenance</h3>
      {provenance.sources.length ? provenance.sources.map(source => <div className="source-reference" key={source.node_id}><button className="text-button" onClick={() => onSelect(source)}>{source.label}</button><p className="muted">{sourceCategory(source)} · {source.node_id}</p>
        {nodeData(source).url && <Details data={{url:nodeData(source).url}} />}</div>) : <p className="muted">No linked source document recorded for this item.</p>}
      <p className="muted">Source categories are recorded metadata, not reliability ratings.</p>
    </section>
    <section><h3>Execution provenance</h3>{provenance.runs.length ? provenance.runs.map(run => <div className="execution-reference" key={run.node_id}>
      <button className="text-button" onClick={() => onSelect(run)}>{run.node_id}</button><Details data={nodeData(run)} />
    </div>) : <p className="muted">Execution provenance unavailable for this item.</p>}
      <Details data={{agent_action:details.agent_action ?? details.action_id, tool:details.tool ?? details.tool_name,
        retrieval_query:details.query ?? details.retrieval_query, validation_state:details.validation_state}} />
      <p className="muted">A model run records execution metadata; it does not validate a proposition. Missing tool/query fields are not reconstructed.</p>
    </section>
    <section><h3>Recorded item fields</h3><Details data={details} /></section>
    <ReviewActions onAction={onAction} item={node} state={reviewState} />
  </aside>;
}
