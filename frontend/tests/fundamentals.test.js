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
