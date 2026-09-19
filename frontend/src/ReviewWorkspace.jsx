import { useState } from 'react';
import { graphCounts, requirementCoverage, summaryFor, labelFor } from './reviewModel.js';

export function ReviewHeader({ graph, review, onChange, persistence, onExport }) {
  const counts = graphCounts(graph);
  const coverage = requirementCoverage(graph);
  return <header className="review-header">
    <div className="review-heading"><div><div className="eyebrow">CLAIMGRAPH / INVESTMENT EVIDENCE REVIEW</div>
      <h1>{review.title}</h1><p className="review-identity">{review.review_id} · Created {new Date(review.created_at).toLocaleString()} · {graph.ticker}</p>
    </div><span className={`status status--${review.status}`}>{labelFor(review.status)}</span></div>
    <div className="review-fields">
      <label>Review title<input value={review.title} onChange={e => onChange({ title:e.target.value })} /></label>
      <label>Reviewer / owner<input placeholder="Enter your name" value={review.owner} onChange={e => onChange({ owner:e.target.value })} /></label>
      <label>Review purpose<input value={review.purpose} onChange={e => onChange({ purpose:e.target.value })} /></label>
      <button onClick={onExport}>Export review + graph</button>
    </div>
    <div className="review-counts">{Object.entries(counts).map(([label, count]) => <div key={label}><strong>{count}</strong><span>{label}</span></div>)}</div>
    <div className="review-footnote"><span>Evidence counts are unique items with recorded support / counter roles; roles may overlap.</span>
      <span>{coverage.total ? `${coverage.satisfied} / ${coverage.total} requirements recorded satisfied · ${coverage.unknown} not assessed` : 'Evidence requirement satisfaction not recorded'}</span>
      <span>{persistence}</span></div>
  </header>;
}

export function ReviewActions({ onAction, item, state }) {
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const actions = item ? [['accepted','Accept'],['challenged','Challenge'],['evidence_requested','Request evidence']]
    : [['approved','Approve for review purpose'],['challenged','Challenge'],['unresolved','Request further investigation']];
  function act(status) {
    try { onAction({ status, note, item }); setError(''); setNote(''); }
    catch (err) { setError(err.message); }
  }
  return <section className="review-actions"><h3>{item ? 'Human review of this item' : 'Human decision'}</h3>
    <p className="muted">{state ? `Recorded state: ${labelFor(state.status ?? state)}` : 'Not reviewed'}</p>
    {state?.note && <p>{state.note} <small>— {state.reviewer}</small></p>}
    <label>Review rationale / evidence needed<textarea rows="3" value={note} onChange={e => setNote(e.target.value)} placeholder="Explain your decision or specify the evidence needed…" /></label>
    <div className="action-buttons">{actions.map(([status,label]) => <button key={status} onClick={() => act(status)}>{label}</button>)}</div>
    {error && <p role="alert" className="review-error">{error}</p>}
    {item && <p className="muted">Accept records your review of this item. It does not change its type, satisfy evidence requirements, or approve the case.</p>}
    {!item && <p className="muted">Approval records human acceptance for the stated purpose. It does not establish objective truth or resolve evidence gaps.</p>}
  </section>;
}

export function ReviewSummary({ graph, review, onChange, onSelect, onAction }) {
  const summary = summaryFor(graph, review.claim_id);
  const choices = graph.nodes.filter(n => ['hypothesis','primary_claim','claim','subclaim'].includes(n.kind));
  const sections = [['Supporting items — selected claim',summary.supporting],['Counter-evidence — selected claim',summary.counter],
    ['Material assumptions — investigation',summary.assumptions],['Missing evidence — investigation',summary.missing],
    ['Calculations — investigation',summary.calculations],['Sources — investigation',summary.sources]];
  return <section className="review-summary">
    <div className="panel-header"><div><h2>Review summary</h2><p>Recorded evidence, limitations, and human disposition</p></div></div>
    <label>Primary analytical claim / candidate hypothesis<select value={review.claim_id ?? ''} onChange={e => onChange({claim_id:e.target.value})}>
      {!choices.length && <option value="">No analytical claim recorded</option>}
      {choices.map(n => <option key={n.node_id} value={n.node_id}>{n.label}</option>)}
    </select></label>
    <p className="primary-statement">{summary.claim?.label ?? 'No analytical claim recorded'}</p>
    <p className="muted">Recorded assessment: {summary.claim?.data?.assessment ?? summary.claim?.assessment ?? (summary.claim?.kind === 'hypothesis' ? 'Candidate explanation — no overall assessment recorded' : 'Not recorded')}.</p>
    <div className="summary-grid">{sections.map(([title,nodes]) => <section key={title}><h3>{title} <span>{nodes.length}</span></h3>
      {nodes.length ? <ul>{nodes.map(n => <li key={n.node_id}><button className="text-button" onClick={() => onSelect(n)}>{n.label}</button></li>)}</ul> : <p className="muted">None recorded. This is not evidence of absence.</p>}
    </section>)}</div>
    <ReviewActions onAction={onAction} state={review.status} />
    <details><summary>Human review history ({review.history.length})</summary>
      {review.history.length ? <ol className="review-history">{review.history.map((entry,i) => <li key={i}><strong>{labelFor(entry.status)}</strong> · {entry.reviewer} · {new Date(entry.at).toLocaleString()}<p>{entry.note}</p><small>{entry.item ?? `Review purpose: ${entry.purpose} · Analytical claim: ${entry.claim_id ?? 'Not recorded'}`}</small></li>)}</ol> : <p className="muted">No human decisions recorded.</p>}
    </details>
  </section>;
}
