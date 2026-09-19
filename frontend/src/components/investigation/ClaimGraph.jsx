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
  colorMode = "light",
  onSelectItem,
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

        colorMode={colorMode}

        fitView
        fitViewOptions={{
          padding: 0.12,
        }}

        minZoom={0.15}
        maxZoom={1.8}

        onNodeClick={(_, node) => {
          onSelectItem?.(
            node.data
          );
        }}

        onEdgeClick={(_, edge) => {
          onSelectItem?.(
            edge.data
          );
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
