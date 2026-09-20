export const DEMO_PORTFOLIO = {id:'sample', name:'Sample research portfolio (fictional allocation)', as_of:'2026-03-20', positions:[{ticker:'COHU',weight:.5},{ticker:'PDFS',weight:.5}]};
export function initialState(storage) {
  try {
    const saved = JSON.parse(storage?.getItem('claimgraph:workspace:v1') ?? 'null');
    if (saved?.portfolio && Array.isArray(saved.workspaces)) return {...saved, route:['/portfolio','/explore',...saved.workspaces.map(w => `/investigate/${w.id}`)].includes(locationRoute()) ? locationRoute() : '/portfolio'};
  } catch { /* Local persistence is best effort. */ }
  return {portfolio:DEMO_PORTFOLIO, selected_as_of:DEMO_PORTFOLIO.as_of, workspaces:[], watched:[], candidate:null, route:['/portfolio','/explore'].includes(locationRoute()) ? locationRoute() : '/portfolio'};
}
export function locationRoute() { return typeof location === 'undefined' ? '/portfolio' : location.pathname; }
export function workspaceReducer(state, action) {
  switch (action.type) {
    case 'navigate': return {...state, route:action.route};
    case 'date': return {...state, candidate:null, selected_as_of:action.value, portfolio:{...state.portfolio,as_of:action.value}};
    case 'portfolio': return {...state, portfolio:action.portfolio};
    case 'candidate': { const date = action.candidate?.requested_as_of ?? action.candidate?.signal_date ?? state.selected_as_of; return {...state, candidate:action.candidate, selected_as_of:date, portfolio:{...state.portfolio,as_of:date}}; }
    case 'open': return {...state, workspaces:[...state.workspaces,action.workspace], route:`/investigate/${action.workspace.id}`};
    case 'snapshot': return {...state, workspaces:state.workspaces.map(w => w.id === action.id ? {...w,...action.patch} : w)};
    case 'close': return {...state, workspaces:state.workspaces.filter(w => w.id !== action.id), route:state.route === `/investigate/${action.id}` ? '/portfolio' : state.route};
    case 'watch': return {...state, watched:[...state.watched.filter(c => c.pair !== action.candidate.pair), action.candidate]};
    default: return state;
  }
}
export function validatePositions(text) {
  const positions = text.trim().split('\n').filter(Boolean).map(line => {
    const [ticker,weight] = line.trim().split(/[\s,]+/);
    return {ticker:ticker.toUpperCase(), weight:Number(weight)};
  });
  if (!positions.length || positions.some(p => !/^[A-Z0-9.^=-]+$/.test(p.ticker) || !Number.isFinite(p.weight) || p.weight < 0) ||
      new Set(positions.map(p => p.ticker)).size !== positions.length || Math.abs(positions.reduce((n,p) => n+p.weight,0)-1) > .001) throw new Error('Use unique tickers and nonnegative decimal weights summing to 1.');
  return positions;
}
export function turnOverlay(graph, turn) {
  if (turn === 'initial') {
    if (graph.followups?.some(f => !f.delta)) return null;
    const laterNodes = new Set((graph.followups ?? []).flatMap(f => f.delta?.added_node_ids ?? []));
    const laterEdges = new Set((graph.followups ?? []).flatMap(f => f.delta?.added_edge_ids ?? []));
    return {added_node_ids:graph.nodes.filter(n => !laterNodes.has(n.node_id)).map(n => n.node_id), added_edge_ids:graph.edges.filter(e => !laterEdges.has(e.edge_id)).map(e => e.edge_id), reassessed_hypothesis_ids:[]};
  }
  return graph.followups?.find(f => f.run_id === turn)?.delta ?? null;
}
export function holdingResearch(workspaces, ticker, cutoff) {
  return workspaces.filter(w => {
    const g = w.graph, event = g?.nodes.find(n => n.kind === 'anomaly')?.data;
    const entities = [g?.ticker, ...(event?.related_entities ?? [])];
    const date = event?.metadata?.observed_at ?? event?.detected_at;
    return entities.includes(ticker) && (!date || date.slice(0,10) <= cutoff);
  });
}
