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
  const response = await fetcher('/api/investigations', { method:'POST',
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
    case 'failure': return {...state, running:false, error:action.error};
    case 'saved': return {...state, error:null, loaded:{graph:action.graph, key:action.key}};
    default: return state;
  }
}
