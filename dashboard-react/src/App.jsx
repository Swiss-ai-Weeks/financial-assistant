import { useMemo, useState } from "react";

import ClaimGraph from "./ClaimGraph";
import NodeInspector from "./NodeInspector";
import { mockClaimGraph } from "./mockClaimGraph";

import "./index.css";


export default function App() {
  const [selectedNode, setSelectedNode] = useState(null);

  const graph = useMemo(
    () => mockClaimGraph,
    []
  );

  const primaryClaim = graph.nodes.find(
    (node) =>
      node.node_id === graph.primary_claim_id
  );

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">
            SIGNAL AVALANCHE
          </div>

          <h1>Market anomaly investigation</h1>
        </div>

        <div className="score-card">
          <span>Leading explanation</span>

          <strong>
            {graph.causal_score.toFixed(1)}
          </strong>

          <small>
            {graph.causal_classification.replaceAll("_", " ")}
          </small>
        </div>
      </header>

      <section className="claim-summary">
        <div className="claim-summary__label">
          Current assessment
        </div>

        <div className="claim-summary__text">
          {primaryClaim?.label}
        </div>

        <div className="claim-summary__qualification">
          This is a qualified causal hypothesis, not an observed fact.
        </div>
      </section>

      <main className="workspace">
        <section className="graph-panel">
          <div className="panel-header">
            <div>
              <h2>ClaimGraph</h2>

              <p>
                Follow the explanation from claim to evidence,
                contradiction and source.
              </p>
            </div>

            <div className="legend">
              <span>Claim</span>
              <span>Evidence</span>
              <span>Counterpoint</span>
              <span>Source</span>
            </div>
          </div>

          <ClaimGraph
            graph={graph}
            onSelectNode={setSelectedNode}
          />
        </section>

        <NodeInspector node={selectedNode} />
      </main>
    </div>
  );
}