import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {graphCounts, summaryFor, provenanceFor, evidenceRoles} from '../src/reviewModel.js';

const kinds = ['claim', 'observation', 'calculation', 'inference'];
const nodes = kinds.map(kind => ({node_id:kind, kind, label:`Native ${kind}`}));
const graph = {nodes:[...nodes, {node_id:'h', kind:'hypothesis'}, {node_id:'doc', kind:'document'},
  {node_id:'run', kind:'model_run', data:{run_id:'MR'}}], edges:[]};
for (const kind of kinds) {
  graph.edges.push({edge_id:`support-${kind}`, source:kind, target:'h', kind:'supports', data:{model_run_id:'MR'}});
  graph.edges.push({edge_id:`counter-${kind}`, source:kind, target:'h', kind:kind === 'inference' ? 'weakens' : 'contradicts'});
  graph.edges.push({edge_id:`context-${kind}`, source:kind, target:'h', kind:'context_for'});
}
graph.edges.push({source:'calculation', target:'observation', kind:'calculated_from'},
  {source:'observation', target:'doc', kind:'extracted_from'},
  {source:'claim', target:'doc', kind:'extracted_from'},
  {source:'inference', target:'calculation', kind:'derived_from'});

test('native support/counter/context counts never require a claim source', () => {
  const counts = graphCounts(graph);
  assert.equal(counts.Evidence, 4);
  assert.equal(counts['Counter-evidence'], 4);
  assert.equal(counts.Context, 4);
  assert.equal(summaryFor(graph, 'h').supporting.length, 4);
  assert.equal(summaryFor(graph, 'h').counter.length, 4);
});
test('execution and requirement links are not epistemic counts', () => {
  const edges = ['produced_by','published_by','extracted_from','requires','candidate_explanation_for'].map(kind => ({source:'claim',target:'h',kind}));
  const roles = evidenceRoles({...graph, edges});
  assert.equal(roles.support.size + roles.counter.size + roles.context.size, 0);
});
test('heterogeneous assessment traverses native source inputs and model run', () => {
  for (const kind of kinds) {
    const edge = graph.edges.find(e => e.edge_id === `support-${kind}`);
    assert.equal(provenanceFor(graph, edge).runs[0].node_id, 'run');
    assert(provenanceFor(graph, edge).sources.some(n => n.node_id === 'doc'));
  }
});
test('inspector explicitly shows assessment types, endpoints and qualification', () => {
  const source = readFileSync(new URL('../src/NodeInspector.jsx', import.meta.url), 'utf8');
  for (const field of ['source_type','source_id','source_content','target_hypothesis','assessment_model_run','missing_information']) assert(source.includes(field));
});
