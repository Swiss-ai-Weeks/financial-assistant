import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createReview, updateReview, graphCounts, filterGraph, provenanceFor, requirementCoverage, summaryFor, sourceCategory, serializeReview, restoreReview } from '../src/lib/claimgraph/reviewModel.js';
const graph = JSON.parse(readFileSync(new URL('../public/examples/investigation_live_nvidia.json', import.meta.url)));

test('review identity and dates belong to review, not anomaly', () => {
  const review = createReview(graph, '2026-09-19T12:00:00Z');
  assert.equal(review.investigation_id, graph.investigation_id);
  assert.equal(review.created_at, '2026-09-19T12:00:00Z');
  assert.equal(review.status, 'needs_review');
  assert.equal(review.owner, '');
  assert.equal(graph.nodes.find(n => n.node_id === review.claim_id).kind, 'hypothesis');
});
test('counts deduplicate evidence roles and preserve original epistemic types', () => {
  const g = { nodes: [{node_id:'a',kind:'claim'}, {node_id:'h',kind:'hypothesis'}, {node_id:'m',kind:'missing_evidence'}],
    edges: [{source:'a',target:'h',kind:'supports'}, {source:'a',target:'h',kind:'supports'}, {source:'a',target:'h',kind:'weakens'}] };
  assert.equal(graphCounts(g).Evidence, 1);
  assert.equal(graphCounts(g)['Counter-evidence'], 1);
  assert.equal(graphCounts(g)['Missing evidence'], 1);
  assert.equal(g.nodes[0].kind, 'claim');
});
test('filters retain only connected edges without mutating graph', () => {
  const original = JSON.stringify(graph);
  const filtered = filterGraph(graph, ['missing_evidence']);
  assert.equal(filtered.nodes.length, 8);
  assert.equal(filtered.edges.length, 0);
  assert.equal(JSON.stringify(graph), original);
  assert.equal(filterGraph(graph), graph);
});
test('provenance follows source and model links including edge assessment runs', () => {
  const claim = graph.nodes.find(n => n.kind === 'claim');
  const provenance = provenanceFor(graph, claim);
  assert.equal(provenance.sources.length, 2);
  assert.equal(provenance.runs[0].data.operation, 'claim_extraction');
  const edge = graph.edges.find(e => e.kind === 'supports');
  assert.equal(provenanceFor(graph, edge).runs[0].data.operation, 'relation_assessment');
  assert.equal(provenanceFor(graph, {node_id:'unknown',data:{}}).runs.length, 0);
});
test('human decisions require identity and rationale, challenges revoke approval', () => {
  let review = createReview(graph);
  assert.throws(() => updateReview(review, {status:'approved',note:'Checked'}), /reviewer/);
  review = {...review, owner:'Research reviewer'};
  assert.throws(() => updateReview(review, {status:'approved',note:''}), /rationale/);
  review = updateReview(review, {status:'approved',note:'Accepted for committee discussion'});
  assert.equal(review.status, 'approved');
  const changed = updateReview(review, {item:graph.nodes[0],status:'challenged',note:'Verify baseline'});
  assert.equal(changed.status, 'challenged');
  assert.equal(changed.history.length, 2);
  assert.equal(review.history.length, 1);
});
test('unknown evidence satisfaction and source classifications are never inferred', () => {
  const g = {nodes:[{kind:'evidence_requirement',data:{}}, {kind:'evidence_requirement',data:{status:'satisfied'}}]};
  assert.deepEqual(requirementCoverage(g), {total:2,satisfied:1,unknown:1});
  assert.equal(sourceCategory({kind:'source',data:{publisher:'nvidia.com'}}), 'Unclassified');
});
test('summary supports are scoped to the selected analytical claim', () => {
  const id = createReview(graph).claim_id;
  const summary = summaryFor(graph, id);
  assert.equal(summary.claim.node_id, id);
  assert.ok(summary.supporting.every(n => graph.edges.some(e => e.source === n.node_id && e.target === id && e.kind === 'supports')));
  assert.equal(summary.missing.length, 8);
});

test('illustrative fixture has support, counter, assumptions, gaps, calculations and source lineage', () => {
  const demo = JSON.parse(readFileSync(new URL('../public/examples/investigation_review_demo.json', import.meta.url)));
  const counts = graphCounts(demo);
  for (const key of ['Evidence','Counter-evidence','Assumptions','Missing evidence','Calculations','Sources']) assert.ok(counts[key] > 0, key);
  assert.match(demo.nodes.find(n => n.kind === 'anomaly').label, /ILLUSTRATIVE/);
  assert.deepEqual(requirementCoverage(demo), {total:2,satisfied:1,unknown:0});
  assert.equal(summaryFor(demo, 'hypothesis:H-REGULATORY').counter.length, 1);
  assert.equal(provenanceFor(demo, demo.nodes.find(n => n.node_id === 'observation:DEMO-PEERS')).sources.length, 2);
  assert.equal(provenanceFor(demo, demo.nodes.find(n => n.node_id === 'observation:DEMO-PEERS')).runs.length, 0);
});
test('every saved graph keeps valid endpoints, unique IDs and can create a review', () => {
  for (const file of ['investigation_temporal_demo.json','investigation_review_demo.json','investigation_live_nvidia.json']) {
    const g = JSON.parse(readFileSync(new URL(`../public/examples/${file}`, import.meta.url)));
    const ids = new Set(g.nodes.map(n => n.node_id));
    assert.equal(ids.size, g.nodes.length);
    assert.equal(new Set(g.edges.map(e => e.edge_id)).size, g.edges.length);
    assert.ok(g.edges.every(e => ids.has(e.source) && ids.has(e.target)), file);
    assert.ok(ids.has(createReview(g).claim_id));
  }
});

test('saved review roundtrips but an approval cannot attach to changed investigation data', () => {
  const review = updateReview({...createReview(graph), owner:'Reviewer'}, {status:'approved',note:'Accepted for this purpose'});
  const saved = serializeReview(graph, review);
  assert.equal(restoreReview(graph, saved).review.status, 'approved');
  const revised = {...graph, nodes:graph.nodes.map((n,i) => i === 0 ? {...n,label:'Revised event'} : n)};
  assert.equal(restoreReview(revised, saved).review.status, 'needs_review');
  assert.match(restoreReview(revised, saved).reason, /differs/);
  assert.equal(restoreReview(graph, '{broken').review.status, 'needs_review');
  const corrupt = JSON.parse(saved); corrupt.review.owner = null;
  assert.equal(restoreReview(graph, JSON.stringify(corrupt)).review.owner, '');
});
test('relationship inspection resolves evidence source documents', () => {
  const relationship = graph.edges.find(e => e.kind === 'supports');
  assert.equal(provenanceFor(graph, {...relationship,inspectorType:'edge'}).sources.length, 2);
});

test('acceptance does not resolve missing evidence or approve a review automatically', () => {
  const item = graph.nodes.find(n => n.kind === 'missing_evidence');
  let review = {...createReview(graph),owner:'Reviewer'};
  const original = JSON.stringify(graph);
  review = updateReview(review, {item,status:'accepted',note:'Accept that this gap remains material'});
  assert.equal(review.status, 'needs_review');
  assert.equal(JSON.stringify(graph), original);
  review = updateReview(review, {item,status:'evidence_requested',note:'Retrieve consensus estimates'});
  assert.equal(review.status, 'unresolved');
  assert.equal(review.history[1].claim_id, review.claim_id);
});
test('legacy v0.1 relation direction and contextual competition are preserved', () => {
  const g = {nodes:[{node_id:'p',kind:'primary_claim'},{node_id:'e',kind:'evidence'},
    {node_id:'c',kind:'counter_evidence'},{node_id:'a',kind:'alternative_explanation'}],
    edges:[{source:'p',target:'e',kind:'supported_by'},{source:'p',target:'c',kind:'contradicted_by'},
      {source:'a',target:'p',kind:'competes_with'}]};
  assert.equal(graphCounts(g)['Counter-evidence'], 1);
  assert.equal(summaryFor(g,'p').supporting[0].node_id,'e');
  assert.equal(summaryFor(g,'p').counter[0].node_id,'c');
  assert.deepEqual(filterGraph(g,['counter']).nodes.map(n => n.node_id),['c']);
});
test('provenance traversal terminates on cycles and does not traverse unrelated support claims', () => {
  const g = {nodes:[{node_id:'c',kind:'calculation'},{node_id:'o',kind:'observation'},
    {node_id:'d',kind:'document'},{node_id:'d2',kind:'document'}],edges:[
    {source:'c',target:'o',kind:'calculated_from'},{source:'o',target:'c',kind:'derived_from'},
    {source:'o',target:'d',kind:'extracted_from'},{source:'d2',target:'c',kind:'supports'}]};
  assert.deepEqual(provenanceFor(g,g.nodes[0]).sources.map(n => n.node_id),['d']);
});

test('accepting an unrelated item cannot hide an outstanding challenge', () => {
  let review = {...createReview(graph),owner:'Reviewer'};
  review = updateReview(review, {item:graph.nodes[0],status:'challenged',note:'Baseline is unsupported'});
  review = updateReview(review, {item:graph.nodes[1],status:'accepted',note:'Source inspected'});
  assert.equal(review.status,'challenged');
});
