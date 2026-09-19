import { useEffect, useState } from 'react';
import DetectorPanel from './DetectorPanel';
import ClaimGraph from './ClaimGraph';
import NodeInspector from './NodeInspector';
import { ReviewHeader, ReviewSummary } from './ReviewWorkspace';
import { createReview, updateReview, itemKey, restoreReview, serializeReview } from './reviewModel.js';
import './App.css';
import './index.css';

const EXAMPLES = [
  ['investigation_live_nvidia.json', 'NVDA · saved NIM run / synthetic attention event'],
  ['investigation_review_demo.json', 'Illustrative review · support, counter-evidence & gaps'],
  ['investigation_gs_ual_2026-03-20.json', 'GS / UAL · saved historical investigation'],
  ['investigation_axp_bac_2026-02-27.json', 'AXP / BAC · saved historical investigation'],
  ['investigation_demo.json', 'Original illustrative investigation'],
];
const storageKey = graph => `claimgraph:review:v1:${graph.investigation_id ?? graph.anomaly_id}`;

function exportReview(graph, review) {
  const blob = new Blob([JSON.stringify({ review, investigation:graph }, null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = `${review.review_id.replace(/[^a-z0-9_-]/gi, '_')}.json`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function App() {
  const [file, setFile] = useState(EXAMPLES[0][0]);
  const [loaded, setLoaded] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/${file}`, {signal:controller.signal}).then(response => {
      if (!response.ok) throw new Error(`Could not load investigation: HTTP ${response.status}`);
      return response.json();
    }).then(graph => {
      if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new Error('Invalid investigation graph');
      setLoaded({file,graph});
    }).catch(err => { if (err.name !== 'AbortError') setError(err.message); });
    return () => controller.abort();
  }, [file]);
  return <div className="app-shell">
    <nav className="case-selector"><label>Saved investigation<select value={file} onChange={e => {setFile(e.target.value); setError(null);}}>
      {EXAMPLES.map(([path,label]) => <option key={path} value={path}>{label}</option>)}
    </select></label><span>Review workspace · local prototype</span></nav>
    {error ? <p className="review-error" role="alert">{error}</p> : loaded?.file === file
      ? <InvestigationWorkspace key={file} graph={loaded.graph} /> : <p className="loading" role="status">Loading investigation…</p>}
  </div>;
}

function InvestigationWorkspace({graph}) {
  const [initial] = useState(() => {
    try {
      return restoreReview(graph, localStorage.getItem(storageKey(graph)));
    } catch { return {review:createReview(graph),reason:'Browser storage unavailable · export to retain a copy'}; }
  });
  const [review, setReview] = useState(initial.review);
  const [persistence, setPersistence] = useState(initial.reason);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [view, setView] = useState('graph');
  function saveReview(next) {
    setReview(next);
    try {
      localStorage.setItem(storageKey(graph), serializeReview(graph, next));
      setPersistence('Stored in this browser only · export to retain a copy');
    } catch { setPersistence('Browser storage unavailable · changes are in memory; export to retain a copy'); }
  }
  const onChange = patch => saveReview({...review, ...patch,
    status: review.status === 'approved' ? 'needs_review' : review.status, updated_at:new Date().toISOString()});
  const onAction = action => saveReview(updateReview(review, action));
  const onSelect = node => {setSelectedNode(node);};
  const anomaly = graph.nodes.find(n => n.kind === 'anomaly');
  return <>
    <ReviewHeader graph={graph} review={review} onChange={onChange} persistence={persistence} onExport={() => exportReview(graph,review)} />
    <section className="claim-summary"><div className="claim-summary__label">Attention event</div>
      <div className="claim-summary__text">{anomaly?.label ?? 'No anomaly recorded'}</div>
      <div className="claim-summary__qualification">An attention event triggers investigation; it does not establish causality. Saved output is replayed here; no model is running.</div>
    </section>
    <details className="detector-drawer"><summary>Explore market anomaly candidates</summary><DetectorPanel onSelectCandidate={setSelectedCandidate} />
      {selectedCandidate && <p className="selected-candidate">Selected candidate: <strong>{selectedCandidate.pair}</strong> · z {selectedCandidate.z_score.toFixed(2)}. Candidate selection does not generate an investigation. The saved review above remains active.</p>}
    </details>
    <main className="workspace"><section className="graph-panel">
      <div className="workspace-tabs"><button aria-pressed={view === 'graph'} onClick={() => setView('graph')}>Evidence graph</button><button aria-pressed={view === 'summary'} onClick={() => setView('summary')}>Review summary</button></div>
      <div hidden={view !== 'graph'}><div className="panel-header"><div><h2>Investigation graph</h2><p>Inspect typed propositions, evidence relationships, sources and execution.</p></div><div className="legend">{graph.nodes.length} nodes · {graph.edges.length} relationships</div></div>
        <ClaimGraph graph={graph} onSelectItem={onSelect} itemReviews={review.item_reviews} />
      </div>
      {view === 'summary' && <ReviewSummary graph={graph} review={review} onChange={onChange} onSelect={onSelect} onAction={onAction} />}
    </section><NodeInspector key={selectedNode ? itemKey(selectedNode) : 'empty'} node={selectedNode} graph={graph} onSelect={onSelect} onAction={onAction}
      reviewState={selectedNode ? review.item_reviews[itemKey(selectedNode)] : null} />
    </main>
  </>;
}
