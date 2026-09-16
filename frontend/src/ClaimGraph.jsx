import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";


function positionNodes(graphNodes) {
  const counters = {};

  const rows = {
    primary_claim: 40,
    subclaim: 200,
    evidence: 380,
    counter_evidence: 380,
    missing_evidence: 380,
    source: 550,
    alternative_explanation: 200,
  };

  return graphNodes.map((node) => {
    const kind = node.kind;

    counters[kind] = counters[kind] || 0;

    const index = counters[kind]++;

    let x = 80 + index * 270;

    if (kind === "primary_claim") {
      x = 350;
    }

    if (kind === "alternative_explanation") {
      x = 900 + index * 250;
    }

    return {
      id: node.node_id,

      position: {
        x,
        y: rows[kind] ?? 300,
      },

      data: {
        ...node,
        label: node.label,
      },

      className: `claim-node claim-node--${kind}`,
    };
  });
}


function convertEdges(graphEdges) {
  return graphEdges.map((edge) => ({
    id: edge.edge_id,
    source: edge.source,
    target: edge.target,

    label: edge.kind.replaceAll("_", " "),

    animated:
      edge.kind === "contradicted_by" ||
      edge.kind === "competes_with",
  }));
}


export default function ClaimGraph({
  graph,
  onSelectNode,
}) {
  const nodes = positionNodes(graph.nodes);
  const edges = convertEdges(graph.edges);

  return (
    <div className="graph-container">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={(_, node) => onSelectNode(node.data)}
        fitView
        fitViewOptions={{
          padding: 0.2,
        }}
      >
        <Background />

        <Controls />

        <MiniMap />
      </ReactFlow>
    </div>
  );
}