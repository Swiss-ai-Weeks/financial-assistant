import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {toReactFlowNodes, toReactFlowEdges} from '../src/graphAdapter.js';
const graph = JSON.parse(readFileSync(new URL('../public/investigation_live_nvidia.json', import.meta.url)));

test('graph layout preserves all node data and has distinct positions for large type groups', () => {
  const nodes = toReactFlowNodes(graph.nodes);
  assert.equal(nodes.length, graph.nodes.length);
  assert.equal(new Set(nodes.map(n => `${n.position.x},${n.position.y}`)).size, nodes.length);
  for (const n of nodes) {
    const original = graph.nodes.find(item => item.node_id === n.id);
    assert.equal(n.data.data, original.data);
    assert.equal(n.data.kind, original.kind);
  }
});
test('relationship adapter preserves rationale and model assessment provenance', () => {
  const edge = graph.edges.find(e => e.kind === 'supports');
  const rendered = toReactFlowEdges([edge])[0];
  assert.equal(rendered.data.model_run_id, edge.data.model_run_id);
  assert.equal(rendered.data.rationale, edge.data.rationale);
  assert.equal(rendered.animated, false);
});
