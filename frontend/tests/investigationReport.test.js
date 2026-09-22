import test from 'node:test';
import assert from 'node:assert/strict';
import {buildInvestigationReport, reportExport} from '../src/lib/claimgraph/investigationReport.js';

const cutoff = '2026-09-20T23:59:59Z';
const node = (node_id,kind,label,data={}) => ({node_id,kind,label,data});
const metric = value => ({status:'available',value});
function investigation() {
  return {investigation_id:'report-test',ticker:'TEST',nodes:[
    node('Q','anomaly','Review investment',{observed_at:cutoff}),
    node('H','hypothesis','Recorded investment thesis'),
    node('E','observation','Revenue increased',{published_at:'2026-09-19T00:00:00Z'}),
    node('CE','observation','Margins declined',{published_at:'2026-09-19T00:00:00Z'}),
    node('A','assumption','Demand persists'),node('G','missing_evidence','Validate margins'),
    node('D','document','Filing',{published_at:'2026-09-19T00:00:00Z'}),
    node('S','source','Issuer'),
  ],edges:[
    {edge_id:'r1',source:'H',target:'E',kind:'supported_by',data:{strength:0.7}},
    {edge_id:'r2',source:'CE',target:'H',kind:'weakens',data:{rationale:'Lower margins weaken the earnings case'}},
    {edge_id:'r3',source:'E',target:'D',kind:'extracted_from'},
    {edge_id:'r4',source:'D',target:'S',kind:'published_by'},
  ]};
}
function addSimulation(graph) {
  graph.nodes.push(node('CALC','calculation','Historical portfolio overlay simulation',{
    status:'available',formula:'combined_daily = portfolio_daily + overlay',
    current:{start:'2026-01-01',end:'2026-09-19',sessions:180,volatility:metric(0.124),max_drawdown:metric(-0.082)},
    combined:{volatility:metric(0.121),max_drawdown:{status:'unavailable',value:999}},
  }));
  graph.edges.push({edge_id:'calc-input',source:'CALC',target:'E',kind:'calculated_from'});
}
test('existing position preserves support, assumptions, opposing rationale and related claim', () => {
  const graph = investigation(), before = structuredClone(graph);
  const r = buildInvestigationReport(graph,{cutoff,reportMode:'existing_position'});
  assert.equal(r.schema_version,'investigation-report-v2');
  assert.equal(r.supporting_evidence[0].node_id,'E');
  assert.deepEqual(r.supporting_evidence[0].source_node_ids,['D','S']);
  assert.equal(r.assumptions[0].node_id,'A');
  assert.equal(r.risk_factors[0].node_id,'CE');
  assert.deepEqual(r.risk_factors[0].claim_ids,['H']);
  assert.match(r.risk_factors[0].rationale,/Lower margins/);
  assert.deepEqual(r.thesis[0].evidence_ids,['E']);
  assert.deepEqual(r.evidence_balance,{supporting:1,counter:1,unresolved:2});
  assert.equal(r.overall_assessment,'MIXED EVIDENCE');
  assert.deepEqual(graph,before);
});
test('new position maps existing simulation without treating missing metrics as zero', () => {
  const graph = investigation(); addSimulation(graph);
  const r = buildInvestigationReport(graph,{cutoff,reportMode:'new_position'});
  assert.equal(r.supporting_evidence[0].node_id,'E');
  assert.equal(r.counter_evidence[0].node_id,'CE');
  assert.equal(r.assumptions[0].node_id,'A');
  const sim = r.portfolio_simulation[0];
  assert.deepEqual(sim.input_ids,['E']);
  assert.equal(sim.rows[1].current,0.124);
  assert.equal(sim.rows[1].simulated,0.121);
  assert.ok(Math.abs(sim.rows[1].change + 0.003)<1e-10);
  assert.equal(sim.rows[2].simulated,null);
  assert.equal(sim.rows[2].change,null);
  assert.equal(buildInvestigationReport(graph,{cutoff}).portfolio_simulation.length,0);
});
test('missing and future simulation remain unavailable', () => {
  const graph = investigation();
  let r = buildInvestigationReport(graph,{cutoff,reportMode:'new_position'});
  assert.deepEqual(r.portfolio_simulation,[]);
  for (const format of ['html','markdown']) assert.match(reportExport(r,format).text,/Portfolio simulation not available/);
  addSimulation(graph);
  graph.nodes.find(n => n.node_id === 'CALC').data.published_at='2026-09-21T00:00:00Z';
  r = buildInvestigationReport(graph,{cutoff,reportMode:'new_position'});
  assert.deepEqual(r.portfolio_simulation,[]);
});
test('references are admitted node IDs and dangling lineage is not emitted', () => {
  const graph=investigation(); addSimulation(graph);
  graph.edges.push({edge_id:'dangling',source:'E',target:'absent',kind:'extracted_from'});
  const r=buildInvestigationReport(graph,{cutoff,reportMode:'new_position'});
  const ids=new Set(graph.nodes.map(n => n.node_id));
  for (const item of [...Object.values(r.sections).flat(),...r.thesis,...r.supporting_evidence,...r.counter_evidence,...r.executive_summary,...r.portfolio_simulation]) {
    for (const id of [item.node_id,...(item.node_ids??[]),...(item.claim_ids??[]),...(item.evidence_ids??[]),...(item.counter_ids??[]),...(item.source_node_ids??[]),...(item.lineage_node_ids??[]),...(item.input_ids??[])].filter(Boolean)) assert.ok(ids.has(id),id);
  }
  assert.throws(()=>buildInvestigationReport(graph,{cutoff,reportMode:'invalid'}));
});
test('exports escape graph text and retain institutional sections and provenance', () => {
  const graph=investigation(); graph.nodes[1].label='<script>alert("x")</script>';
  const r=buildInvestigationReport(graph,{cutoff});
  const html=reportExport(r,'html').text;
  assert.ok(!html.includes('<script>'));
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/Risk factors \/ counter-evidence/);
  assert.match(html,/id="D"/);
  assert.match(html,/href="#E"/);
});
