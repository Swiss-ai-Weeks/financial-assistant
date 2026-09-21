import assert from 'node:assert/strict';
import {test} from 'node:test';
import {discover} from '../src/pythia/discovery.js';
import {initialState,workspaceReducer} from '../src/workspaceStore.js';
const pair = (a,b,z=2) => ({ticker_a:a,ticker_b:b,pair:`${a}/${b}`,z_score:z,correlation:.8,cointegration_p:.01,signal_date:'2026-03-20',mode:'historical',scan_id:'test-scan'});
function fixture(candidates, missing=[]) {
  const calls=[];
  return {calls,request:async (path,options) => {
    calls.push({path,options});
    if(path==='/api/anomalies/historical-scan') return {ok:true,json:async()=>({candidates,as_of:'2026-03-20'})};
    const ticker=new URL(path,'http://test').searchParams.get('q');
    return {ok:true,json:async()=>({securities:missing.includes(ticker) ? [{ticker:'WRONG',identity:'WRONG'}] : [{ticker,identity:ticker,name:ticker}]})};
  }};
}
test('Lucky filters, ranks, resolves exact identities and preserves cutoff without graph calls',async()=>{
  const f=fixture([pair('HELD','B',9),pair('C','D',2),pair('E','F',4),pair('BAD','X',12),pair('LOW','X',.5)],['BAD']);
  const result=await discover({asOf:'2026-03-20',positions:[{ticker:'HELD'}],request:f.request});
  assert.equal(result.candidate.pair,'E/F');
  assert.equal(result.candidate.requested_as_of,'2026-03-20');
  assert.equal(result.candidate.mode,'historical');
  assert.equal(result.candidate.scan_id,'test-scan');
  assert.equal(result.alreadyHeld,false);
  assert.deepEqual(result.securities.map(s=>s.identity),['E','F']);
  assert.deepEqual(JSON.parse(f.calls[0].options.body),{as_of:'2026-03-20',entry:1.5,corr_min:.65,alpha:.05});
  assert(f.calls.every(c=>c.path.startsWith('/api/instruments/search?') || c.path==='/api/anomalies/historical-scan'));
});
test('Held candidates are labelled, empty/unresolved scans do not invent a security',async()=>{
  const f=fixture([pair('A','B')]);
  assert.equal((await discover({asOf:'2026-03-20',positions:[{ticker:'A'}],request:f.request})).alreadyHeld,true);
  for(const f of [fixture([]),fixture([pair('A','B')],['A'])]) assert.equal((await discover({asOf:'2026-03-20',request:f.request})).candidate,null);
  await assert.rejects(discover({asOf:'2026-03-20',request:async()=>({ok:false,json:async()=>({error:'No cache'})})}),/No cache/);
});
test('Discovery inspection and explicit workspace handoff preserve saved graph and model',async()=>{
  let state=workspaceReducer(initialState(),{type:'open',workspace:{id:'saved',model:{id:'chosen'},graph:{nodes:[{node_id:'claim'}],edges:[]}}});
  const before=structuredClone(state.workspaces);
  const result=await discover({asOf:'2026-03-20',request:fixture([pair('A','B')]).request});
  state=workspaceReducer(state,{type:'navigate',route:'/past'});
  assert.deepEqual(state.workspaces,before);
  state=workspaceReducer(state,{type:'open',workspace:{id:'lucky',candidate:result.candidate,as_of:result.candidate.requested_as_of}});
  assert.equal(state.route,'/investigate/lucky');
  assert.deepEqual(state.workspaces[0],before[0]);
  assert.equal(state.workspaces[1].graph,undefined);
  assert.deepEqual(initialState({getItem:()=>JSON.stringify(state)}).workspaces,state.workspaces);
});
