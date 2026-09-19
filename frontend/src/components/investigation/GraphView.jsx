import { useState } from "react";

import ClaimGraph from "./ClaimGraph";
import NodeInspector from "./NodeInspector";

/**
 * Full audit trail of one investigation: every claim,
 * explanation, source and model run, and how they relate.
 */
export default function GraphView({ investigation, theme }) {
  const [selected, setSelected] = useState(null);

  if (!investigation?.graph) {
    return (
      <div className="graph-view graph-view--empty">
        <div className="empty">
          <h2>No ClaimGraph yet</h2>
          <p>
            Explain an anomaly from the desk. The graph shows which article
            supports which explanation, what contradicts it, what is still
            assumed, and which model run produced every node.
          </p>
        </div>
      </div>
    );
  }

  const { graph, anomaly } = investigation;

  return (
    <div className="graph-view">
      <header className="graph-view__header">
        <div>
          <span className="eyebrow">ClaimGraph · schema {graph.schema_version}</span>
          <h2>{anomaly.summary}</h2>
        </div>
        <div className="graph-view__counts mono">
          <span>{graph.nodes.length} nodes</span>
          <span>{graph.edges.length} edges</span>
        </div>
      </header>

      <div className="graph-view__body">
        <ClaimGraph
          key={investigation.investigation_id}
          graph={graph}
          colorMode={theme}
          onSelectItem={setSelected}
        />
        <NodeInspector node={selected} />
      </div>
    </div>
  );
}
