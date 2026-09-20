// Review metadata is a human-owned overlay; the investigation remains immutable.
export const REVIEW_STATUSES = ['new', 'investigating', 'needs_review', 'challenged', 'approved', 'unresolved'];
export const labelFor = (value) => String(value ?? '').replaceAll('_', ' ');
export const nodeData = (node) => node?.data ?? node ?? {};
export const itemKey = (item) => `${item.inspectorType === 'edge' ? 'edge' : 'node'}:${item.edge_id ?? item.node_id}`;

export function createReview(graph, now = new Date().toISOString()) {
  const claim = graph.nodes.find(n => n.node_id === graph.primary_claim_id)
    ?? graph.nodes.find(n => n.kind === 'hypothesis')
    ?? graph.nodes.find(n => ['primary_claim', 'claim'].includes(n.kind));
  return {
    review_id: `REV-${graph.investigation_id ?? graph.anomaly_id}`,
    investigation_id: graph.investigation_id ?? graph.anomaly_id,
    title: `${graph.ticker ?? 'Analytical'} evidence review`,
    owner: '', created_at: now, updated_at: now, status: 'needs_review',
    claim_id: claim?.node_id ?? null, purpose: 'Investment research',
    item_reviews: {}, history: [],
  };
}

export function updateReview(review, action, now = new Date().toISOString()) {
  if (!review.owner.trim()) throw new Error('Enter a reviewer name before recording a decision.');
  if (!action.note?.trim()) throw new Error('Record a rationale or the evidence you need.');
  const next = { ...review, updated_at: now };
  if (action.item) {
    if (!['accepted', 'challenged', 'evidence_requested'].includes(action.status)) throw new Error('Invalid item review state.');
    next.item_reviews = { ...review.item_reviews, [itemKey(action.item)]: {
      status: action.status, note: action.note.trim(), reviewer: review.owner.trim(), at: now,
    } };
    const states = Object.values(next.item_reviews).map(item => item.status);
    next.status = states.includes('challenged') ? 'challenged'
      : states.includes('evidence_requested') ? 'unresolved' : 'needs_review';
  } else {
    if (!REVIEW_STATUSES.includes(action.status)) throw new Error('Invalid review status.');
    if (action.status === 'approved' && !review.purpose.trim()) throw new Error('Enter the purpose for which you accept this analysis.');
    next.status = action.status;
  }
  next.history = [...review.history, { status: action.status, item: action.item ? itemKey(action.item) : null,
    note: action.note.trim(), reviewer: review.owner.trim(), purpose: review.purpose, claim_id:review.claim_id, at: now }];
  return next;
}

export function evidenceRoles(graph) {
  const support = new Set(graph.nodes.filter(n => n.kind === 'evidence').map(n => n.node_id));
  const counter = new Set(graph.nodes.filter(n => n.kind === 'counter_evidence').map(n => n.node_id));
  for (const e of graph.edges) {
    if (e.kind === 'supports') support.add(e.source);
    if (e.kind === 'supported_by') support.add(e.target);
    if (['contradicts', 'weakens'].includes(e.kind)) counter.add(e.source);
    if (e.kind === 'contradicted_by') counter.add(e.target);
  }
  if (graph.temporalStatuses) {
    for (const role of [support, counter]) for (const id of role) {
      if (!['available_at_cutoff', 'derived_from_available_evidence'].includes(graph.temporalStatuses.get(id))) role.delete(id);
    }
  }
  return { support, counter };
}

export function graphCounts(graph) {
  const count = (...kinds) => graph.nodes.filter(n => kinds.includes(n.kind)).length;
  const roles = evidenceRoles(graph);
  return { Claims: count('claim', 'primary_claim', 'subclaim'), Hypotheses: count('hypothesis'),
    Evidence: roles.support.size, 'Counter-evidence': roles.counter.size,
    Assumptions: count('assumption'), 'Missing evidence': count('missing_evidence'),
    Calculations: count('calculation'), Sources: count('source') };
}

export function requirementCoverage(graph) {
  const requirements = graph.nodes.filter(n => n.kind === 'evidence_requirement');
  return { total: requirements.length,
    satisfied: requirements.filter(n => nodeData(n).status === 'satisfied').length,
    unknown: requirements.filter(n => !['satisfied', 'unsatisfied', 'partial'].includes(nodeData(n).status)).length };
}

export function filterGraph(graph, filters = []) {
  if (!filters.length) return graph;
  const { support, counter } = evidenceRoles(graph);
  const nodes = graph.nodes.filter(n => filters.some(f => f === 'support' ? support.has(n.node_id)
    : f === 'counter' ? counter.has(n.node_id) : f === n.kind));
  const ids = new Set(nodes.map(n => n.node_id));
  return { ...graph, nodes, edges: graph.edges.filter(e => ids.has(e.source) && ids.has(e.target)) };
}

export function sourceCategory(node) {
  const explicit = nodeData(node).source_classification;
  if (['PRIMARY', 'MARKET_DATA', 'SECONDARY', 'COMMENTARY', 'DERIVED', 'INTERNAL'].includes(explicit)) return explicit;
  // Display classification, not an assessment of reliability.
  if (['calculation', 'inference'].includes(node.kind)) return 'DERIVED';
  return 'Unclassified';
}

export function provenanceFor(graph, item) {
  const byId = new Map(graph.nodes.map(n => [n.node_id, n]));
  const data = nodeData(item);
  const relationships = graph.edges.filter(e => e.source === item.node_id || e.target === item.node_id);
  const visited = new Set();
  const visit = id => {
    if (visited.has(id)) return;
    visited.add(id);
    for (const e of graph.edges) {
      if (e.source === id && ['extracted_from', 'published_by', 'sourced_from', 'calculated_from', 'derived_from'].includes(e.kind)) visit(e.target);
    }
  };
  if (item.node_id) visit(item.node_id);
  else if (item.edge_id) { visit(item.source); visit(item.target); }
  const sources = [...visited].map(id => byId.get(id)).filter(n => n && ['document', 'source'].includes(n.kind));
  const runIds = new Set(relationships.filter(e => e.source === item.node_id && e.kind === 'produced_by').map(e => e.target));
  const run = graph.nodes.find(n => n.kind === 'model_run' && nodeData(n).run_id === data.model_run_id);
  if (run) runIds.add(run.node_id);
  if (item.kind === 'model_run') runIds.add(item.node_id);
  return { relationships, sources, runs: [...runIds].map(id => byId.get(id)).filter(Boolean) };
}

export function summaryFor(graph, claimId) {
  const claim = graph.nodes.find(n => n.node_id === claimId);
  const related = graph.edges.filter(e => e.source === claimId || e.target === claimId);
  const supportIds = new Set(related.filter(e => e.target === claimId && e.kind === 'supports').map(e => e.source));
  const counterIds = new Set(related.filter(e => e.target === claimId && ['contradicts', 'weakens'].includes(e.kind)).map(e => e.source));
  for (const e of related) {
    if (e.source === claimId && e.kind === 'supported_by') supportIds.add(e.target);
    if (e.source === claimId && e.kind === 'contradicted_by') counterIds.add(e.target);
  }
  return { claim, supporting: graph.nodes.filter(n => supportIds.has(n.node_id)),
    counter: graph.nodes.filter(n => counterIds.has(n.node_id)),
    assumptions: graph.nodes.filter(n => n.kind === 'assumption'),
    missing: graph.nodes.filter(n => n.kind === 'missing_evidence'),
    calculations: graph.nodes.filter(n => n.kind === 'calculation'),
    sources: graph.nodes.filter(n => n.kind === 'source') };
}

export function serializeReview(graph, review) {
  return JSON.stringify({ review, investigation: graph });
}

export function restoreReview(graph, stored, now) {
  const fresh = reason => ({ review:createReview(graph, now), reason });
  if (!stored) return fresh('New local review · edit or record a decision to save in this browser');
  try {
    const payload = JSON.parse(stored);
    const r = payload.review;
    if (JSON.stringify(payload.investigation) !== JSON.stringify(graph)) {
      return fresh('Saved investigation differs · previous decisions have not been applied');
    }
    if (!r || r.investigation_id !== (graph.investigation_id ?? graph.anomaly_id)
      || typeof r.review_id !== 'string' || !r.review_id
      || !REVIEW_STATUSES.includes(r.status) || typeof r.owner !== 'string'
      || typeof r.title !== 'string' || typeof r.purpose !== 'string'
      || !r.item_reviews || typeof r.item_reviews !== 'object' || Array.isArray(r.item_reviews)
      || Object.values(r.item_reviews).some(item => !item || !['accepted','challenged','evidence_requested'].includes(item.status) || typeof item.note !== 'string')
      || !Array.isArray(r.history) || r.history.some(e => !e || typeof e.note !== 'string' || typeof e.reviewer !== 'string')
      || !Number.isFinite(Date.parse(r.created_at))
      || (r.claim_id !== null && !graph.nodes.some(n => n.node_id === r.claim_id))) {
      return fresh('Saved review is invalid · new local review created');
    }
    return {review:r, reason:'Stored in this browser only · export to retain a copy'};
  } catch {
    return fresh('Saved review could not be read · new local review created');
  }
}
