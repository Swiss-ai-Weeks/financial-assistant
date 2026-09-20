import test from 'node:test';
import assert from 'node:assert/strict';
import {candidatePayload, selectModel, requestInvestigation, investigationReducer} from '../src/investigationClient.js';
import {createReview} from '../src/reviewModel.js';

const candidate = {ticker_a:'GS', ticker_b:'UAL', signal_date:'2026-03-20', threshold:1.7};
const models = [{provider:'nvidia-nim', model:'nemotron'}, {provider:'other', model:'alternative'}];
const observed = '2026-03-20T21:00:00+00:00';
const graph = {investigation_id:'new-run', nodes:[{node_id:'run',kind:'model_run',data:{provider:'other'}}, {node_id:'claim',kind:'claim'}], edges:[{source:'claim',target:'run',kind:'produced_by'}]};

test('candidate payload carries tickers, date, aware observation, threshold and selection', () => {
  assert.deepEqual(candidatePayload(candidate, models[0], observed), {
    ticker_a:'GS', ticker_b:'UAL', as_of:'2026-03-20', observed_at:observed,
    provider:'nvidia-nim', model:'nemotron', entry:1.7,
  });
  assert.throws(() => candidatePayload(candidate, models[0], '2026-03-20T21:00:00'), /timezone/);
  assert.throws(() => candidatePayload(candidate, models[0], '2026-03-21T21:00:00Z'), /candidate date/);
});
test('model/provider selection changes next request without mutating recorded provenance', () => {
  const before = JSON.stringify(graph);
  const selected = selectModel(models, 'other', 'alternative');
  assert.equal(candidatePayload(candidate, selected, observed).model, 'alternative');
  assert.equal(JSON.stringify(graph), before);
  assert.throws(() => selectModel(models, 'nvidia-nim', 'alternative'));
});
test('investigation posts JSON to the live endpoint and preserves the entire returned graph', async () => {
  const payload = candidatePayload(candidate, models[0], observed);
  const result = await requestInvestigation(payload, async (url, options) => {
    assert.equal(url, '/api/investigations');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), payload);
    return {ok:true, json:async () => graph};
  });
  assert.equal(result, graph);
});
test('running retains old graph; success replaces graph and opens a fresh review', () => {
  const old = {loaded:{graph:{nodes:[], edges:[]}, key:'saved'}};
  const running = investigationReducer(old, {type:'start'});
  assert.equal(running.loaded, old.loaded);
  assert.equal(running.running, true);
  const done = investigationReducer(running, {type:'success', graph, key:'new'});
  assert.equal(done.loaded.graph, graph);
  assert.equal(done.loaded.fresh, true);
  assert.equal(done.running, false);
  assert.deepEqual(createReview(done.loaded.graph).item_reviews, {});
});
test('request errors and invalid responses retain the old graph and review identity', async () => {
  for (const response of [{ok:false, json:async () => ({error:'Retrieval failed'})}, {ok:true,json:async () => ({})}]) {
    const old = {loaded:{graph, key:'old'}};
    let state = investigationReducer(old, {type:'start'});
    try { await requestInvestigation({}, async () => response); assert.fail('Expected error'); }
    catch (error) { state = investigationReducer(state, {type:'failure',error:error.message}); }
    assert.equal(state.loaded, old.loaded);
    assert.equal(state.running, false);
    assert.ok(state.error);
  }
});
