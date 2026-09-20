import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { temporalView, temporalStatuses, temporalSummary, timelineSteps } from '../src/temporalModel.js';
import { filterGraph, createReview, serializeReview, restoreReview } from '../src/reviewModel.js';
import { validateGraph } from '../src/investigationClient.js';
const cutoff = '2026-09-16T12:00:00Z';
const node = (id, kind, data={}) => ({node_id:id,kind,label:id,data});
const edge = (source,target,kind) => ({edge_id:`${source}-${target}`,source,target,kind});
const graph = {investigation_id:'temporal-test',anomaly_id:'a',nodes:[node('a','anomaly',{observed_at:cutoff}),
  node('before','document',{published_at:'2026-09-15T10:00:00Z'}),node('after','document',{published_at:'2026-09-18T10:00:00Z'}),
  node('unknown','document',{retrieved_at:'2026-09-14T10:00:00Z'}),node('calc','calculation'),node('good','inference'),node('h','hypothesis'),
  node('outcome','observation',{published_at:'2026-09-15T10:00:00Z',temporal_role:'hindsight_outcome'})],
  edges:[edge('calc','before','calculated_from'),edge('calc','after','calculated_from'),edge('good','before','derived_from'),edge('before','h','supports'),edge('outcome','h','supports')]};
const visible = (id,time=cutoff) => temporalView(graph,time).nodes.some(n=>n.node_id===id);
test('pre-cutoff evidence remains visible; future and undated evidence excluded',()=>{
 assert.ok(visible('before')); assert.ok(!visible('after')); assert.ok(!visible('unknown'));
 assert.equal(temporalStatuses(graph,cutoff).get('unknown'),'date_unknown');
 assert.ok(visible('after','latest'));
});
test('retrieval date is never publication; event date also cannot establish availability',()=>{
 const g={...graph,nodes:[node('x','document',{event_at:cutoff,retrieved_at:cutoff})]};
 assert.equal(temporalStatuses(g,'latest').get('x'),'date_unknown');
});
test('all calculation inputs required; inference with eligible input is derived',()=>{
 assert.ok(!visible('calc')); assert.ok(visible('calc','latest'));
 assert.equal(temporalStatuses(graph,cutoff).get('good'),'derived_from_available_evidence');
});
test('missing inputs and cycles stay unknown',()=>{
 const g={nodes:[node('x','calculation'),node('y','inference')],edges:[edge('x','y','derived_from'),edge('y','x','derived_from')]};
 assert.equal(temporalStatuses(g,cutoff).get('x'),'date_unknown');
});
test('type and role filters compose with temporal view',()=>{
 assert.deepEqual(filterGraph(temporalView(graph,cutoff),['support']).nodes.map(n=>n.node_id),['before']);
 assert.deepEqual(filterGraph(temporalView(graph,cutoff),['document']).nodes.map(n=>n.node_id),['before']);
});
test('cutoff changes do not mutate graph, selected item, or stored human review',()=>{
 const review=createReview(graph); const selected=graph.nodes[1]; const snapshot=serializeReview(graph,review);
 for(const step of timelineSteps(graph)) temporalView(graph,step.value);
 assert.equal(serializeReview(graph,review),snapshot); assert.equal(graph.nodes[1],selected);
 assert.deepEqual(restoreReview(graph,snapshot).review,review);
});
test('hindsight outcomes never enter evidence graph or contemporaneous counts',()=>{
 assert.ok(!visible('outcome')); assert.ok(!visible('outcome','latest'));
 assert.equal(temporalSummary(graph,cutoff).support,1);
});
test('date-only evidence not eligible during publication day',()=>{
 const g={nodes:[node('d','document',{published_at:'2026-09-16T00:00:00Z',published_date_only:true})],edges:[]};
 assert.equal(temporalView(g,cutoff).nodes.length,0);
 assert.equal(temporalView(g,'2026-09-17T00:00:00Z').nodes.length,1);
});
test('every existing saved fixture and fictional temporal replay loads',()=>{
 for(const name of fs.readdirSync(new URL('../public/',import.meta.url)).filter(n=>n.startsWith('investigation_')&&n.endsWith('.json'))){
  const g=validateGraph(JSON.parse(fs.readFileSync(new URL(`../public/${name}`,import.meta.url))));
  for(const step of timelineSteps(g)) assert.doesNotThrow(()=>temporalView(g,step.value));
 }
});
