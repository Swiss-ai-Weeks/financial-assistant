import assert from 'node:assert/strict';
import { sourceHref } from '../src/sourceLinks.js';
import { candidatePayload } from '../src/investigationClient.js';
import { temporalSummary, temporalStatuses } from '../src/temporalModel.js';

assert.equal(sourceHref('https://corpus.test/documents/NEWS-123', 'https://corpus.test'), '/api/bookreader/documents/NEWS-123');
assert.equal(sourceHref('https://public.test/article', 'https://corpus.test'), 'https://public.test/article');
assert.equal(sourceHref('https://corpus.test/documents/../secret', 'https://corpus.test'), null);
assert.equal(sourceHref('javascript:alert(1)', ''), null);
const request = candidatePayload({mode:'historical', scan_id:'snapshot', requested_as_of:'2026-01-04',
  signal_date:'2026-01-02', ticker_a:'AAA', ticker_b:'BBB'}, {provider:'nim', model:'nemotron'}, '');
assert.equal(request.as_of, '2026-01-04');
assert.equal(request.scan_id, 'snapshot');
assert.equal(request.observed_at, undefined); // The server owns date-only semantics.
const graph = {nodes:[{node_id:'doc', kind:'document', data:{published_at:'2026-01-06', published_date_only:true}}], edges:[]};
assert.equal(temporalStatuses(graph, '2026-01-06T12:00:00Z').get('doc'), 'appeared_after_cutoff');
assert.equal(temporalStatuses(graph, '2026-01-06T23:59:59.999Z').get('doc'), 'available_at_cutoff');
assert.deepEqual(temporalSummary({...graph, hindsight_outcome:{return_pct:100}}, 'latest'), temporalSummary(graph, 'latest'));
