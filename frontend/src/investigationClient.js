export function selectModel(models, provider, model) {
  const selected = models.find(item => item.provider === provider && item.model === model);
  if (!selected) throw new Error('Select a configured model/provider');
  return selected;
}

export function candidatePayload(candidate, selection, observedAt) {
  if (!candidate?.ticker_a || !candidate?.ticker_b || !candidate?.signal_date) throw new Error('Select a candidate');
  if (!selection?.provider || !selection?.model) throw new Error('Select a model/provider');
  if (candidate.mode === 'historical') return {mode:'historical', scan_id:candidate.scan_id,
    as_of:candidate.requested_as_of, ticker_a:candidate.ticker_a, ticker_b:candidate.ticker_b,
    provider:selection.provider, model:selection.model};
  if (!/(Z|[+-]\d{2}:\d{2})$/.test(observedAt) || !Number.isFinite(Date.parse(observedAt))) {
    throw new Error('Observed at must be a valid timestamp with a timezone offset');
  }
  if (observedAt.slice(0, 10) !== candidate.signal_date) throw new Error('Observed at must fall on the candidate date');
  return { ticker_a:candidate.ticker_a, ticker_b:candidate.ticker_b,
    as_of:candidate.signal_date, observed_at:observedAt,
    provider:selection.provider, model:selection.model, entry:candidate.threshold };
}

export function validateGraph(graph) {
  if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new Error('Invalid investigation graph');
  return graph;
}

export async function requestInvestigation(payload, fetcher = fetch) {
  const response = await fetcher(payload.requirement_id ? '/api/investigations/followup' : '/api/investigations', { method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
  const graph = await response.json();
  if (!response.ok) throw new Error(graph.error ?? `Investigation failed: HTTP ${response.status}`);
  return validateGraph(graph);
}

// Preserve the current graph and its review identity until a complete result arrives.
export function investigationReducer(state, action) {
  switch (action.type) {
    case 'start': return {...state, running:true, error:null};
    case 'success': return {...state, running:false, error:null,
      loaded:{graph:action.graph, key:action.key, fresh:true}};
    case 'followup': return {...state, running:false, error:null, loaded:{...state.loaded, graph:action.graph}};
    case 'failure': return {...state, running:false, error:action.error};
    case 'saved': return {...state, error:null, loaded:{graph:action.graph, key:action.key}};
    default: return state;
  }
}

// Status requests are observational and have their own cancellation lifecycle.
export function pollInvestigation(runId, onStatus, {fetcher = fetch, schedule = setTimeout, cancel = clearTimeout} = {}) {
  let stopped = false;
  let timer;
  let controller;
  const stop = () => { stopped = true; cancel(timer); controller?.abort(); };
  async function poll() {
    controller = new AbortController();
    try {
      const response = await fetcher(`/api/investigations/status/${encodeURIComponent(runId)}`, {signal:controller.signal, cache:'no-store'});
      if (response.ok) {
        const status = await response.json();
        if (!stopped) {
          onStatus(status);
          if (status.state === 'complete' || status.state === 'failed') stop();
        }
      }
    } catch { /* A missing/unavailable status never interrupts the POST. */ }
    if (!stopped) timer = schedule(poll, 1000);
  }
  poll();
  return stop;
}

export function startInvestigation(payload, onStatus, options = {}) {
  const request = {...payload, run_id:crypto.randomUUID()};
  onStatus({run_id:request.run_id, state:'running', stage:'preparing', completed:[], metrics:{},
    started_at:new Date().toISOString()});
  const stop = pollInvestigation(request.run_id, onStatus, options);
  const result = requestInvestigation(request, options.fetcher).finally(stop);
  return {result, stop};
}

export const executionStages = [
  ['preparing', 'Preparing investigation'],
  ['research_plan', 'Research plan created', 'research_tasks', 'tasks'],
  ['retrieval', 'Retrieval complete', 'search_hits', 'hits'],
  ['evidence_selection', 'Historical evidence selected', 'documents_selected', 'documents'],
  ['claim_extraction', 'Grounded claims extracted', 'claims', 'claims'],
  ['hypothesis_generation', 'Competing hypotheses generated', 'hypotheses', 'hypotheses'],
  ['hypothesis_audit', 'Auditing assumptions and evidence gaps', 'audits', 'audits'],
  ['relationship_assessment', 'Assessing relationships', 'relationships', 'relationships'],
  ['graph_build', 'Building ClaimGraph', 'nodes', 'nodes'],
];
export function progressRows(status, historical) {
  const stages = status.followup ? [
    ['followup_preparing', 'Preparing follow-up'],
    ['research_plan', 'Building research tasks'],
    ['fundamentals', 'Retrieving peer fundamentals'],
    ['retrieval', 'Searching BookReader and web'],
    ['evidence_selection', 'Selecting evidence'],
    ['claim_extraction', 'Extracting grounded claims'],
    ['relationship_assessment', 'Reassessing affected hypotheses'],
    ['resolution_assessment', 'Assessing resolution'],
    ['graph_build', 'Updating ClaimGraph'],
  ] : historical ? [...executionStages,
    ['hindsight', 'Held-out hindsight outcome (not original-investigation evidence)'],
    ['replay_save', 'Saving replay packet']] : executionStages;
  const current = status.stage === 'graph_complete' ? 'graph_build' : status.stage?.replace(/_complete$/, '');
  return stages.map(([id, label, metric, unit]) => {
    const completed = status.state === 'complete' || status.completed?.includes(id);
    const active = current === id;
    const state = active && status.state === 'failed' ? 'failed' : completed ? 'completed' : active ? 'current' : 'pending';
    return {id, label:active && !completed && status.message ? status.message : label, state,
      symbol:{failed:'✕',completed:'✓',current:'●',pending:'○'}[state],
      detail:status.metrics?.[metric] != null ? `${status.metrics[metric]} ${unit}` : ''};
  });
}
