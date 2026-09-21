import { originalCutoff, timelineSteps, temporalSummary, temporalStatuses } from './temporalModel.js';

export default function TemporalReview({graph, cutoff, onChange, onSelect}) {
  const then = temporalSummary(graph, originalCutoff(graph));
  const now = temporalSummary(graph, 'latest');
  const before = temporalStatuses(graph, originalCutoff(graph));
  const later = graph.nodes.filter(n => n.kind === 'document' && before.get(n.node_id) === 'appeared_after_cutoff');
  const outcomes = graph.nodes.filter(n => before.get(n.node_id) === 'hindsight_outcome');
  return <section className="temporal-review">
    <h2>Evidence timeline</h2><p>Inspect publication availability inside this investigation. Use Time Travel above to reconstruct a historical market and run a new investigation.</p>
    <div className="action-buttons">{timelineSteps(graph).map(step => <button key={step.value} aria-pressed={cutoff === step.value} onClick={() => onChange(step.value)}>{step.label}</button>)}</div>
    <p>Inspection cutoff: <strong>{cutoff || 'Unavailable'}</strong> · Original cutoff: {originalCutoff(graph) ?? 'Unavailable'}</p>
    <p>Earlier views exclude future and undated evidence. Hypotheses, gaps and executions remain investigation context, not contemporaneous facts. Derived availability describes inputs, not when the analysis was performed.</p>
    <div className="summary-grid"><section><h3>THEN</h3><p>{then.evidence} available items · {then.support} supporting · {then.counter} contradicting / weakening · {then.gaps} recorded gaps</p></section>
      <section><h3>NOW / HINDSIGHT</h3><p>{now.evidence} dated items · {now.support} supporting · {now.counter} contradicting / weakening · {later.length} later documents</p>
        <p>Gap resolution and changes in relationship strength are not inferred. Recorded gaps remain open unless separately assessed.</p>
        {later.map(n => <p key={n.node_id}><button className="text-button" onClick={() => onSelect(n)}>{n.label}</button></p>)}
      </section></div>
    {cutoff === 'latest' && <section className="hindsight-outcomes"><h3>Hindsight outcomes — excluded from evidence counts and graph support</h3>
      {outcomes.length ? outcomes.map(n => <p key={n.node_id}><button onClick={() => onSelect(n)}>{n.label}</button></p>) : <p>No market outcome recorded in this graph.</p>}
      <p>Realised outcomes do not prove a hypothesis or imply it should have been predicted.</p></section>}
  </section>;
}
