import { test } from 'node:test';
import assert from 'node:assert/strict';
import { provenanceFor } from '../src/reviewModel.js';
import { temporalStatuses } from '../src/temporalModel.js';
import { sourceHref } from '../src/sourceLinks.js';

const graph = {
  nodes: [
    {node_id:'calculation:roic', kind:'calculation', data:{metadata:{formula_version:'roic-v1'}}},
    {node_id:'calculation:nopat', kind:'calculation', data:{}},
    {node_id:'observation:income', kind:'observation', data:{}},
    {node_id:'document:filing', kind:'document', data:{published_at:'2026-02-20T23:59:59.999999Z', published_date_only:true}},
    {node_id:'source:sec', kind:'source', data:{publisher:'SEC EDGAR'}},
  ],
  edges: [
    {source:'calculation:roic', target:'calculation:nopat', kind:'calculated_from'},
    {source:'calculation:nopat', target:'observation:income', kind:'calculated_from'},
    {source:'observation:income', target:'document:filing', kind:'extracted_from'},
    {source:'document:filing', target:'source:sec', kind:'published_by'},
  ],
};

test('ROIC provenance traverses intermediate calculations to filing and SEC', () => {
  const provenance = provenanceFor(graph, graph.nodes[0]);
  assert.deepEqual(provenance.sources.map(n => n.node_id), ['document:filing','source:sec']);
  assert.equal(provenance.relationships[0].target, 'calculation:nopat');
});

test('financial calculation availability follows filing rather than fiscal period end', () => {
  for (const cutoff of ['2026-01-15T23:59:59Z','2026-02-20T21:00:00Z']) {
    assert.equal(temporalStatuses(graph, cutoff).get('calculation:roic'), 'appeared_after_cutoff');
  }
  assert.equal(temporalStatuses(graph, '2026-02-21T00:00:00Z').get('calculation:roic'), 'derived_from_available_evidence');
});

test('SEC filing index opens using the existing safe source link contract', () => {
  const url = 'https://www.sec.gov/Archives/edgar/data/1/000000000125000001/0000000001-25-000001-index.html';
  assert.equal(sourceHref(url, ''), url);
  assert.equal(sourceHref('javascript:alert(1)', ''), null);
});

import { quarterlyView } from '../src/graphAdapter.js';
import { temporalView } from '../src/temporalModel.js';

test('quarterly disclosure retains hidden atomic evidence and reveals full quarter lineage', () => {
  const graph = {nodes:[
    {node_id:'company',kind:'context',data:{subtype:'fundamentals'}},
    {node_id:'q1',kind:'context',data:{subtype:'fundamental_snapshot',entity:'AAA',period_end:'2025-03-31',older_quarter:true}},
    {node_id:'q2',kind:'context',data:{subtype:'fundamental_snapshot',entity:'AAA',period_end:'2025-06-30'}},
    {node_id:'obs',kind:'observation',data:{metadata:{provider:'SEC EDGAR'}}},
    {node_id:'doc',kind:'document',data:{published_at:'2025-08-01T00:00:00Z',metadata:{provider:'SEC EDGAR'}}},
    {node_id:'trend',kind:'calculation',data:{metadata:{metric_id:'revenue_qoq_growth',frequency:'quarterly',ticker:'AAA',period_end:'2025-06-30'}}},
  ], edges:[
    {source:'q2',target:'obs',kind:'derived_from'},
    {source:'obs',target:'doc',kind:'extracted_from'},
    {source:'trend',target:'obs',kind:'calculated_from'},
  ]};
  const initial = quarterlyView(graph);
  assert.deepEqual(initial.nodes.map(n => n.node_id), ['company','q2','trend']);
  assert.equal(graph.nodes.length, 6);
  assert.ok(quarterlyView(graph,{showOlder:true}).nodes.some(n => n.node_id === 'q1'));
  assert.ok(quarterlyView(graph,{expanded:['q2']}).nodes.some(n => n.node_id === 'obs'));
  assert.ok(quarterlyView(graph,{expanded:['q2']}).nodes.some(n => n.node_id === 'doc'));
  assert.equal(quarterlyView(graph,{showAtomic:true}).nodes.length,6);
  assert.ok(!temporalView(graph,'2025-07-01T00:00:00Z').nodes.some(n => n.node_id === 'q2'));
  assert.ok(temporalView(graph,'2025-08-02T00:00:00Z').nodes.some(n => n.node_id === 'q2'));
});
