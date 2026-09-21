import { useEffect, useState } from 'react';
import { sourceHref } from './sourceLinks.js';
import { originalCutoff, temporalStatuses } from './temporalModel.js';
import { nodeData, provenanceFor, sourceCategory, labelFor } from './reviewModel.js';
import { ReviewActions } from './ReviewWorkspace';

function renderValue(value) {
  if (value === null || value === undefined) return 'Not recorded';
  if (typeof value === 'object') return <pre className="inspector-json">{JSON.stringify(value,null,2)}</pre>;
  return String(value);
}
let sourceConfiguration;
function sourceConfig() {
  sourceConfiguration ??= fetch('/api/bookreader/source-links').then(r => r.json());
  return sourceConfiguration;
}
function Details({data}) {
  const [base, setBase] = useState(null);
  useEffect(() => {sourceConfig().then(p => setBase(p.base_url ?? '')).catch(() => {});}, []);
  return Object.entries(data).map(([key,value]) => <div className="inspector-row" key={key}>
    <span>{labelFor(key)}</span><div>{['url','source_uri'].includes(key) && /^https?:\/\//i.test(String(value))
      ? <a href={base === null && !/^https:\/\/www\.sec\.gov\//i.test(String(value)) ? undefined : sourceHref(value, base ?? '') ?? undefined} target="_blank" rel="noreferrer">Open source ↗</a> : renderValue(value)}</div>
  </div>);
}

export default function NodeInspector({node, graph, onSelect, onAction, reviewState, onInvestigate, followupDisabled, cutoff = 'latest'}) {
  if (!node) return <aside className="inspector"><div className="node-type">Inspector</div><h2>Select a node or relationship</h2>
    <p className="muted">Inspect observations, calculations, assumptions, and inferences. Follow sources and model runs, then record a human review.</p>
    <p className="muted">Evidence roles belong to relationships: one item can support one hypothesis and weaken another.</p></aside>;
  const isEdge = node.inspectorType === 'edge';
  const details = isEdge ? {...node.data, ...Object.fromEntries(Object.entries(node).filter(([key]) => !['data','inspectorType','displayKind','label','edge_id'].includes(key)))}
    : node.data ?? Object.fromEntries(Object.entries(node).filter(([key]) => !['node_id','kind','label','inspectorType','displayKind','support','counter','humanState'].includes(key)));
  const financial = details.metadata?.metric_id || details.metadata?.concept ? details.metadata : null;
  const provenance = provenanceFor(graph,node);
  const selectId = id => {const target = graph.nodes.find(n => n.node_id === id); if (target) onSelect(target);};
  return <aside className="inspector">
    <div className="node-type">{isEdge ? 'Relationship' : labelFor(node.kind)}</div><h2>{node.label ?? labelFor(node.kind)}</h2>
    {!isEdge && ['missing_evidence', 'evidence_requirement'].includes(node.kind) && <section>
      <h3>{labelFor(details.resolution_status ?? 'unresolved')}</h3>
      <p>{node.label}</p>
      <button disabled={followupDisabled || !onInvestigate} onClick={() => onInvestigate(node.node_id)}>Investigate this question</button>
      <p>One bounded research cycle. New questions require another human action.</p>
      {details.resolution && <><p>{details.resolution.summary}</p>
        {details.resolution.remaining_question && <p>Still unresolved: {details.resolution.remaining_question}</p>}
        {['supporting_item_ids', 'contradicting_item_ids'].map(key => <div key={key}><h4>{key === 'supporting_item_ids' ? 'Found' : 'Counterpoint'}</h4>
          {details.resolution[key]?.map(id => <button key={id} onClick={() => selectId(id)}>{graph.nodes.find(n => n.node_id === id)?.label ?? id}</button>)}</div>)}
      </>}
      <h4>Follow-up history</h4>
      {(details.followup_history ?? []).map(id => <div key={id}><button onClick={() => selectId(id)}>{id}</button>
        <Details data={graph.nodes.find(n => n.node_id === id)?.data?.counts ?? {}} /></div>)}
    </section>}
    <section className="temporal-review"><h3>Temporal provenance — full recorded item</h3>
      <Details data={{inspection_cutoff:cutoff || 'Unavailable', temporal_status:isEdge ? 'Relationship endpoints must both be eligible' : temporalStatuses(graph, cutoff).get(node.node_id),
        published_at:details.published_date_only ? `${String(details.published_at).slice(0,10)} (date only; time unavailable)` : details.published_at ?? 'Unavailable',
        event_at:details.event_at ?? 'Unavailable', observed_at:details.observed_at ?? originalCutoff(graph) ?? 'Unavailable', retrieved_at:details.retrieved_at ?? 'Unavailable'}} />
      <p>Inspector retains future and hidden items for audit. Retrieval time never establishes publication time.</p>
    </section>
    {details.subtype === 'fundamental_snapshot' && <section><h3>Quarterly financial snapshot</h3>
      <Details data={{company:details.entity, fiscal_year:details.fiscal_year, fiscal_quarter:details.fiscal_quarter,
        period_start:details.period_start, period_end:details.period_end, filings:details.filings,
        available_at:details.available_at, availability_cutoff:details.availability_cutoff,
        unavailable_metrics:details.unavailable_metrics}} />
      {['Income statement', 'Balance sheet', 'Cash flow'].map(section => <div key={section}><h4>{section}</h4>
        {Object.entries(details.metrics ?? {}).filter(([metric]) => {
          const cashFlow = /cash_flow|capex/.test(metric);
          const balance = /cash|assets|liabilities|debt|equity|shares_outstanding|receivable|inventory|payable|lease/.test(metric);
          return section === 'Cash flow' ? cashFlow : section === 'Balance sheet' ? balance && !cashFlow : !balance && !cashFlow;
        }).map(([metric, id]) => <button className="text-button" key={metric} onClick={() => selectId(`${id.startsWith('SEC-') ? 'observation' : 'calculation'}:${id}`)}>{labelFor(metric)}</button>)}
      </div>)}<p className="muted">Click a quarter in the graph to expand or collapse its underlying SEC evidence.</p>
    </section>}
    {financial && <section><h3>Financial evidence</h3><Details data={{
      metric:financial.display_name ?? financial.concept,
      value:financial.value == null ? 'Unavailable' : financial.unit === 'ratio' ? `${(financial.value * 100).toFixed(2)}%` : `${financial.value.toLocaleString()} ${financial.unit}`,
      period_start:financial.period_start, period_end:financial.period_end, comparison_period:financial.comparison_period,
      source_observation_ids:financial.input_fact_ids, taxonomy:financial.taxonomy, unit:financial.unit,
      amended:financial.amended, restatement_status:financial.restatement_status, historically_available:financial.historically_available, formula_version:financial.formula_version,
      formula:financial.formula, available_since:financial.available_at,
      xbrl_tag:financial.tag, filed_at:financial.filed_at, form:financial.form,
      accession:financial.accession, execution:financial.execution, assumptions:financial.assumptions, warnings:financial.warnings,
    }} /><p className="muted">Follow calculated-from relationships to inspect component values and SEC filings.</p></section>}
    <Details data={{[isEdge ? 'edge_id' : 'node_id']:node.edge_id ?? node.node_id}} />
    {!isEdge && ['source','document','calculation','inference'].includes(node.kind) && <Details data={{display_source_category:sourceCategory(node)}} />}
    {isEdge && ['supports', 'weakens', 'contradicts', 'context_for'].includes(node.kind) && <section>
      <h3>Evidence assessment</h3>
      <Details data={{source_type:graph.nodes.find(n => n.node_id === node.source)?.kind,
        source_id:node.source, source_content:graph.nodes.find(n => n.node_id === node.source)?.label,
        relation:node.kind, target_hypothesis:graph.nodes.find(n => n.node_id === node.target)?.label,
        target_id:node.target, strength:details.strength, rationale:details.rationale,
        assumptions:details.assumptions, missing_information:details.missing_information,
        assessment_model_run:details.model_run_id}} />
    </section>}
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
