import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";

import {
  toReactFlowEdges,
  toReactFlowNodes,
} from "./graphAdapter";


export default function ClaimGraph({
  graph,
  onSelectNode,
}) {
  const nodes =
    toReactFlowNodes(graph.nodes);

  const edges =
    toReactFlowEdges(graph.edges);

  return (
    <div className="graph-container">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{
          padding: 0.15,
        }}
        minZoom={0.2}
        maxZoom={1.8}
        onNodeClick={(_, node) => {
          onSelectNode?.(node.data);
        }}
      >
        <Background />

        <Controls />

        <MiniMap
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
}
