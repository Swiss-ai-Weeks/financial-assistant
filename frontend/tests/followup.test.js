import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {investigationReducer, requestInvestigation, progressRows} from '../src/investigationClient.js';
import {temporalView} from '../src/temporalModel.js';

const original = {nodes:[], edges:[]};
const state = {loaded:{graph:original, key:'stable'}, running:false};
const started = investigationReducer(state, {type:'start'});
assert.equal(started.loaded.graph, original);
assert.equal(investigationReducer(started, {type:'failure', error:'failure'}).loaded.graph, original);
const merged = {...original, followups:[{run_id:'R'}]};
const finished = investigationReducer(started, {type:'followup', graph:merged});
assert.equal(finished.loaded.key, 'stable');
assert.equal(finished.loaded.graph, merged);
await requestInvestigation({graph:original, requirement_id:'M'}, async (url, options) => {
  assert.equal(url, '/api/investigations/followup');
  assert.equal(JSON.parse(options.body).requirement_id, 'M');
  return {ok:true, json:async () => merged};
});
assert(progressRows({followup:true, stage:'resolution_assessment', state:'running'}).some(r => r.id === 'resolution_assessment' && r.state === 'current'));
assert(!progressRows({followup:true, stage:'retrieval', state:'running'}).some(r => r.id === 'hypothesis_generation'));
assert.equal(temporalView({nodes:[{node_id:'A', kind:'agent_action', data:{created_at:'2026-09-20T00:00:00Z'}}], edges:[]}, '2020-01-01T00:00:00Z').nodes.length, 1);
const inspector = readFileSync(new URL('../src/NodeInspector.jsx', import.meta.url), 'utf8');
assert(inspector.includes('Investigate this question'));
assert(inspector.includes('followupDisabled'));
const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
assert(app.includes('key={loaded.key}'));
assert.deepEqual(JSON.parse(JSON.stringify(merged)).followups, merged.followups);
