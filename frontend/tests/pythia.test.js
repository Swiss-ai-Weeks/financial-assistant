import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {NAVIGATION, holdingCandidate} from '../src/pythia/deskClient.js';
import {initialState, workspaceReducer as reduce} from '../src/workspaceStore.js';
import {applyCopilotAction} from '../src/copilotContext.js';
import {buildInvestigationReport, reportExport} from '../src/investigationReport.js';
const source = file => readFileSync(new URL(`../src/${file}`,import.meta.url),'utf8');
assert.deepEqual(NAVIGATION.map(([,label])=>label),['Now','Past','Portfolio','Explore','Investigate']);
let state=initialState();
state=reduce(state,{type:'open',workspace:{id:'a',model:{id:'model-a'},graph:{nodes:[],edges:[]}}});
state=reduce(state,{type:'open',workspace:{id:'b',model:{id:'model-b'}}});
state=reduce(state,{type:'navigate',route:'/investigate/a'});
for (const [route] of NAVIGATION.slice(0,4)) {
  state=reduce(state,{type:'navigate',route});
  assert.equal(state.route,route);
  assert.equal(state.workspaces[0].model.id,'model-a');
  assert.equal(state.workspaces[1].model.id,'model-b');
}
state=reduce(state,{type:'navigate',route:'/investigate'});
assert.equal(state.route,'/investigate/a');
state=reduce(state,{type:'snapshot',id:'a',patch:{model:{id:'changed'}}});
assert.equal(state.workspaces[1].model.id,'model-b');
assert.deepEqual(initialState({getItem:()=>JSON.stringify(state)}).workspaces,state.workspaces);
assert.equal(holdingCandidate('NVDA','2026-01-01').requested_as_of,'2026-01-01');
const shell=source('WorkspaceShell.jsx');
assert(shell.includes('hidden={state.route !== \'/now\'}'));
assert(shell.includes('hidden={state.route !== \'/past\'}'));
assert(shell.includes("hidden={!state.route.startsWith('/investigate')}"));
assert(shell.includes('state.workspaces.map(w => <section key={w.id} hidden='));
const desk=source('pythia/MarketDesk.jsx');
assert(desk.includes("mode === 'past' ? 'historical' : 'live'"));
assert(desk.includes('onInvestigate(selected)'));
const graph=JSON.parse(readFileSync(new URL('../public/investigation_review_demo.json',import.meta.url),'utf8'));
const before=JSON.stringify(graph);
let calls=0;
assert.throws(()=>applyCopilotAction({type:'select_node',node_id:'unknown'},graph,{select:()=>calls++}));
assert.throws(()=>applyCopilotAction({type:'open_provenance',node_id:'unknown'},graph,{select:()=>calls++}));
assert.throws(()=>applyCopilotAction({type:'add_claim'},graph,{}));
assert.equal(calls,0); assert.equal(JSON.stringify(graph),before);
const report=buildInvestigationReport(graph,{workspaceId:'a'});
for(const [key,kind] of [['observations','observation'],['calculations','calculation'],['inferences','inference']]) {
 assert(report.sections[key].length>0,key);
 assert(report.sections[key].every(n=>n.kind===kind));
}
for(const items of Object.values(report.sections)) for(const item of items) {
 assert(item.node_id || item.edge_id);
 for(const id of item.source_node_ids) assert(graph.nodes.some(n=>n.node_id===id));
}
assert(report.sections.execution.every(n=>['model_run','tool_call','agent_action','research_task'].includes(n.kind)));
assert(report.sections.supporting_evidence.every(n=>graph.edges.some(e=>e.edge_id===n.edge_id)));
assert.equal(JSON.stringify(graph),before);
for(const format of ['html','markdown','json']) {
 const result=reportExport(report,format);
 assert(result.text.includes(graph.investigation_id));
 assert(result.text.includes(report.sections.calculations[0].node_id));
}
assert(reportExport(report,'html').text.includes('window.print()'));
assert.equal(JSON.parse(reportExport(report,'json').text).graph_snapshot.nodes.length,graph.nodes.length);
const malicious=structuredClone(report);malicious.title='<script>alert(1)</script>';
assert(!reportExport(malicious,'html').text.includes('<script>'));
assert.throws(()=>buildInvestigationReport(graph,{cutoff:'latest'}));
const early=buildInvestigationReport(graph,{cutoff:'2000-01-01T00:00:00Z'});
assert.equal(early.sections.observations.length,0);
assert(early.exclusions.length>0);
assert(!source('investigationReport.js').includes('fetch('));
