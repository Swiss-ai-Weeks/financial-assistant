import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCopilotViewContext, applyCopilotAction } from '../src/copilotContext.js';
import { voiceAPIs } from '../src/copilotClient.js';
import { workspaceReducer } from '../src/workspaceStore.js';
import fs from 'node:fs';
const graph = {nodes:[{node_id:'h',kind:'hypothesis',label:'Hypothesis'}, {node_id:'s',kind:'claim',label:'Support',data:{published_at:'2026-01-01T00:00:00Z'}}, {node_id:'c',kind:'claim',label:'Counter',data:{published_at:'2026-01-01T00:00:00Z'}}],edges:[{source:'s',target:'h',kind:'supports'}, {source:'c',target:'h',kind:'weakens'}]};
test('compact selected context and bounded neighbourhood', () => {
  const context = buildCopilotViewContext({graph,selected:graph.nodes[0],cutoff:'latest'});
  assert.equal(context.selection.id,'h'); assert.equal(context.neighbourhood.length,2);
  assert.equal(context.graph_summary.supporting,1);assert.equal(context.graph_summary.weakening,1);
  const huge = {...graph,nodes:[...graph.nodes,...Array.from({length:1000},(_,i)=>({node_id:`n${i}`,kind:'hypothesis',label:'x'.repeat(10000),data:{private_body:'secret'}}))]};
  const bounded = buildCopilotViewContext({graph:huge,cutoff:'latest'});
  assert.ok(new TextEncoder().encode(JSON.stringify(bounded)).length <= 22000);
  assert.ok(bounded.nodes.length <= 20); assert.ok(!JSON.stringify(bounded).includes('private_body'));
});
test('actions change only view handlers', () => {
  const original = JSON.stringify(graph), calls = [];
  const handlers = {select:n=>calls.push(n.node_id),filters:f=>calls.push(f),fit:()=>calls.push('fit')};
  for (const action of [{type:'select_node',node_id:'h'},{type:'show_supporting'},{type:'show_counter'},{type:'clear_filters'},{type:'fit_graph'}]) applyCopilotAction(action,graph,handlers);
  assert.deepEqual(calls,['h',['support'],['counter'],[],'fit']); assert.equal(JSON.stringify(graph),original);
  assert.throws(()=>applyCopilotAction({type:'select_node',node_id:'bad'},graph,handlers));
});
test('voice absence and workspace isolation', () => {
  assert.deepEqual(voiceAPIs({}),{Recognition:undefined,synthesis:undefined});
  const state = {workspaces:[{id:'a'},{id:'b'}]};
  const next = workspaceReducer(state,{type:'snapshot',id:'a',patch:{copilot:{answer:'a'}}});
  assert.equal(next.workspaces[1].copilot,undefined);
});
test('panel includes text fallback, routing disclosure and commentary label', () => {
  const source = fs.readFileSync(new URL('../src/CopilotPanel.jsx',import.meta.url),'utf8');
  assert.match(source,/onSubmit=\{ask\}/);assert.match(source,/reply.model.label/);assert.match(source,/not admitted evidence/);assert.match(source,/disabled=\{!Recognition/);
});
test('selected future item explains historical exclusion', () => {
  const future = {node_id:'future',kind:'claim',label:'Later report',data:{published_at:'2026-09-01T00:00:00Z'}};
  const context = buildCopilotViewContext({graph:{...graph,nodes:[...graph.nodes,future]},selected:future,cutoff:'2026-01-02T00:00:00Z'});
  assert.equal(context.selection.data.temporal_status,'appeared_after_cutoff');
  assert.equal(context.graph_summary.counts.claim,2);
});
