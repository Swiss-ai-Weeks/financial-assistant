import { useEffect, useReducer, useRef, useState } from 'react';
import { candidatePayload, selectModel, startInvestigation, investigationReducer, validateGraph } from './investigationClient.js';
import InvestigationProgress from './InvestigationProgress';
import TemporalReview from './TemporalReview';
import { originalCutoff, temporalView } from './temporalModel.js';
import DetectorPanel from './DetectorPanel';
import ClaimGraph from './ClaimGraph';
import NodeInspector from './NodeInspector';
import { ReviewHeader, ReviewSummary } from './ReviewWorkspace';
import { createReview, updateReview, itemKey, restoreReview, serializeReview } from './reviewModel.js';
import './App.css';
import './index.css';

const EXAMPLES = [
  ['investigation_temporal_demo.json', 'Fictional temporal replay · teaching case'],
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
  const savedRequest = useRef(null);
  const progressStop = useRef(null);
  const [progress, setProgress] = useState(null);
  const [executionContext, setExecutionContext] = useState(null);
  useEffect(() => () => progressStop.current?.(), []);
  const [file, setFile] = useState(EXAMPLES[0][0]);
  const [{loaded, error, running}, dispatch] = useReducer(investigationReducer, {loaded:null, error:null, running:false});
  const [replays, setReplays] = useState([]);
  const [models, setModels] = useState([]);
  const [selection, setSelection] = useState(null);
  const [modelError, setModelError] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [observedAt, setObservedAt] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/replays', {signal:controller.signal}).then(r => r.json()).then(p => setReplays(p.replays ?? [])).catch(() => {});
    fetch('/api/investigations/models', {signal:controller.signal}).then(async response => {
      if (!response.ok) throw new Error('Could not load configured models');
      const payload = await response.json();
      if (!payload.models?.length) throw new Error('No inference models configured');
      setModels(payload.models); setSelection(payload.models[0]);
    }).catch(err => { if (err.name !== 'AbortError') setModelError(err.message); });
    return () => controller.abort();
  }, []);
  async function investigateCandidate() {
    savedRequest.current?.abort();
    dispatch({type:'start'});
    try {
      const payload = candidatePayload(selectedCandidate, selection, observedAt);
      setExecutionContext(payload);
      const execution = startInvestigation(payload, setProgress);
      progressStop.current = execution.stop;
      const graph = await execution.result;
      setProgress(previous => ({...previous, state:"complete", stage:"complete", updated_at:new Date().toISOString(),
        completed:previous.completed}));
      dispatch({type:'success', graph, key:crypto.randomUUID()});
      if (graph.replay_id) setReplays(previous => [{id:graph.replay_id, label:`${selectedCandidate.pair} · ${graph.historical.as_of} · saved historical run`}, ...previous]);
      setFile('');
    } catch (err) {
      setProgress(previous => previous ? {...previous, state:'failed', updated_at:new Date().toISOString()} : null);
      dispatch({type:'failure', error:err.message});
    }
  }
  useEffect(() => {
    if (!file) return;
    const controller = new AbortController();
    savedRequest.current = controller;
    fetch(file.startsWith('/api/') ? file : `/${file}`, {signal:controller.signal}).then(response => {
      if (!response.ok) throw new Error(`Could not load investigation: HTTP ${response.status}`);
      return response.json();
    }).then(graph => {
      if (!controller.signal.aborted) dispatch({type:'saved', graph:validateGraph(graph), key:file});
    }).catch(err => { if (err.name !== 'AbortError') dispatch({type:'failure', error:err.message}); });
    return () => controller.abort();
  }, [file]);
  return <div className="app-shell">
    <nav className="case-selector"><label>Saved investigation<select value={file} disabled={running} onChange={e => setFile(e.target.value)}>
      <option value="" disabled>Live investigation</option>
      {replays.map(item => <option key={item.id} value={`/api/replays/${item.id}`}>{item.label}</option>)}
      {EXAMPLES.map(([path,label]) => <option key={path} value={path}>{label}</option>)}
    </select></label><label>Import replay<input type="file" accept="application/json" disabled={running} onChange={async e => {
      try { const packet = JSON.parse(await e.target.files[0].text()); setFile('');
        dispatch({type:'saved', graph:validateGraph(packet.investigation ?? packet), key:crypto.randomUUID()});
      } catch (err) {dispatch({type:'failure', error:err.message});}
    }} /></label><span>Review workspace · local prototype</span></nav>
    <details className="detector-drawer" open><summary>Explore market anomaly candidates</summary>
      <DetectorPanel onSelectCandidate={candidate => {setSelectedCandidate(candidate); setObservedAt(candidate ? `${candidate.signal_date}T23:59:59+00:00` : "");}} />
      <label>Model/provider for the next investigation<select disabled={running || !models.length} value={selection ? JSON.stringify(selection) : ''}
        onChange={e => {const next = JSON.parse(e.target.value); setSelection(selectModel(models, next.provider, next.model));}}>
        {!selection && <option value="">Loading configured models…</option>}
        {models.map(item => <option key={JSON.stringify(item)} value={JSON.stringify(item)}>{item.provider} · {item.model}</option>)}
      </select></label>
      {modelError && <p role="alert">{modelError}</p>}
      {selectedCandidate && <div className="selected-candidate">Selected candidate: <strong>{selectedCandidate.pair}</strong> · {selectedCandidate.signal_date}
        {selectedCandidate.mode !== 'historical' && <label>Observed at / evidence cutoff (timezone required)<input value={observedAt} disabled={running} onChange={e => setObservedAt(e.target.value)} /></label>}
        <p>Evidence cutoff: end of {selectedCandidate.requested_as_of ?? selectedCandidate.signal_date} in UTC. Date-only publications retain their uncertainty.</p>
      </div>}
      <button disabled={running || !selectedCandidate || !selection} onClick={investigateCandidate}>{selectedCandidate?.mode === 'historical' ? `Investigate at ${selectedCandidate.requested_as_of}` : 'Investigate candidate'}</button>
    </details>
    {progress && executionContext && <InvestigationProgress status={progress} context={executionContext} />}
    {error && <p className="review-error" role="alert">{error}</p>}
    {loaded ? <InvestigationWorkspace key={loaded.key} graph={loaded.graph} fresh={loaded.fresh} /> : <p className="loading" role="status">Loading investigation…</p>}

  </div>;
}

function InvestigationWorkspace({graph, fresh}) {
  const [initial] = useState(() => {
    if (fresh) return {review:createReview(graph), reason:'New investigation · new institutional review'};
    try {
      return restoreReview(graph, localStorage.getItem(storageKey(graph)));
    } catch { return {review:createReview(graph),reason:'Browser storage unavailable · export to retain a copy'}; }
  });
  const [cutoff, setCutoff] = useState(() => originalCutoff(graph) ?? '');
  const inspectionGraph = temporalView(graph, cutoff);
  const [review, setReview] = useState(initial.review);
  const [persistence, setPersistence] = useState(initial.reason);
  const [selectedNode, setSelectedNode] = useState(null);
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
    <ReviewHeader graph={inspectionGraph} review={review} onChange={onChange} persistence={persistence} onExport={() => exportReview(graph,review)} />
    <section className="claim-summary"><div className="claim-summary__label">Attention event</div>
      <div className="claim-summary__text">{anomaly?.label ?? 'No anomaly recorded'}</div>
      <div className="claim-summary__qualification">An attention event triggers investigation; it does not establish causality. Recorded model_run nodes describe the execution that produced this graph. The model selection above applies to the next investigation.</div>
    </section>
    {graph.historical && <section className="temporal-review"><h2>Investigation as of {graph.historical.as_of}</h2>
      <p>Evidence cutoff: {graph.historical.observed_at} · Market session: {graph.historical.resolved_session}</p>
      <p>{graph.historical.universe_limitation}</p>
      <p>Replay saved: {graph.replay_id}. Export review to download the complete replay packet.</p>
    </section>}
    {graph.hindsight_outcome && <details className="hindsight-outcomes"><summary>Reveal HINDSIGHT OUTCOME — NOT AVAILABLE TO THE ORIGINAL INVESTIGATION</summary>
      <p>Future information — excluded from investigation. Returns do not prove or disprove its hypotheses.</p>
      {graph.hindsight_outcome.unavailable ? <p>{graph.hindsight_outcome.unavailable}</p> : <>
        <p>Entry: next common market session open · {graph.hindsight_outcome.entry_date} · {graph.hindsight_outcome.strategy_direction}</p>
        <table><thead><tr><th>Horizon</th><th>Return</th></tr></thead><tbody>
          {[1,5,10,20].map(h => <tr key={h}><td>{h} sessions</td><td>{graph.hindsight_outcome.forward_returns.find(p => p.horizon_observations === h)?.return_pct.toFixed(2) ?? 'Unavailable'}%</td></tr>)}
          <tr><td>Latest ({graph.hindsight_outcome.latest_date})</td><td>{graph.hindsight_outcome.return_to_latest_pct.toFixed(2)}%</td></tr>
          <tr><td>Max drawdown</td><td>{graph.hindsight_outcome.max_drawdown_pct.toFixed(2)}%</td></tr>
        </tbody></table><p>Reverted: {graph.hindsight_outcome.mean_reversion_date ?? 'Not within available history'}</p>
      </>}
    </details>}
    <TemporalReview graph={graph} cutoff={cutoff} onChange={setCutoff} onSelect={onSelect} />
    <main className="workspace"><section className="graph-panel">
      <div className="workspace-tabs"><button aria-pressed={view === 'graph'} onClick={() => setView('graph')}>Evidence graph</button><button aria-pressed={view === 'summary'} onClick={() => setView('summary')}>Review summary</button></div>
      <div hidden={view !== 'graph'}><div className="panel-header"><div><h2>Investigation graph</h2><p>Inspect typed propositions, evidence relationships, sources and execution.</p></div><div className="legend">{graph.nodes.length} nodes · {graph.edges.length} relationships</div></div>
        <ClaimGraph graph={graph} cutoff={cutoff} onSelectItem={onSelect} itemReviews={review.item_reviews} />
      </div>
      {view === 'summary' && <ReviewSummary graph={inspectionGraph} review={review} onChange={onChange} onSelect={onSelect} onAction={onAction} />}
    </section><NodeInspector key={selectedNode ? itemKey(selectedNode) : 'empty'} node={selectedNode} graph={graph} cutoff={cutoff} onSelect={onSelect} onAction={onAction}
      reviewState={selectedNode ? review.item_reviews[itemKey(selectedNode)] : null} />
    </main>
  </>;
}
