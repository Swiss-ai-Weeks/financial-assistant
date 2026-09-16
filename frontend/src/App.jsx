import {
  useEffect,
  useState,
} from "react";

import ClaimGraph from "./ClaimGraph";
import NodeInspector from "./NodeInspector";

import "./App.css";
import "./index.css";


export default function App() {
  const [graph, setGraph] =
    useState(null);

  const [
    selectedNode,
    setSelectedNode,
  ] = useState(null);

  const [
    error,
    setError,
  ] = useState(null);


  useEffect(() => {
    fetch("/investigation_demo.json")
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            `Could not load graph: `
            + `HTTP ${response.status}`
          );
        }

        return response.json();
      })
      .then(setGraph)
      .catch((err) => {
        console.error(err);
        setError(err.message);
      });
  }, []);


  if (error) {
    return (
      <div className="app-shell">
        <h1>ClaimGraph</h1>

        <p>
          Failed to load investigation:
          {" "}
          {error}
        </p>
      </div>
    );
  }


  if (!graph) {
    return (
      <div className="app-shell">
        <h1>ClaimGraph</h1>

        <p>
          Loading investigation…
        </p>
      </div>
    );
  }


  const anomaly = graph.nodes.find(
    (node) =>
      node.kind === "anomaly"
  );


  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">
            CLAIMGRAPH
          </div>

          <h1>
            Market anomaly investigation
          </h1>
        </div>

        <div className="score-card">
          <span>Ticker</span>

          <strong>
            {graph.ticker}
          </strong>

          <small>
            schema {graph.schema_version}
          </small>
        </div>
      </header>


      <section className="claim-summary">
        <div className="claim-summary__label">
          Attention event
        </div>

        <div className="claim-summary__text">
          {anomaly?.label
            ?? "Unknown anomaly"}
        </div>

        <div
          className=
            "claim-summary__qualification"
        >
          The anomaly triggers an
          investigation. It does not
          itself establish causality.
        </div>
      </section>


      <main className="workspace">
        <section className="graph-panel">
          <div className="panel-header">
            <div>
              <h2>
                Investigation graph
              </h2>

              <p>
                Inspect claims,
                hypotheses, source
                provenance, calculations
                and model provenance.
              </p>
            </div>

            <div className="legend">
              <span>
                {graph.nodes.length} nodes
              </span>

              <span>
                {graph.edges.length} edges
              </span>
            </div>
          </div>

          <ClaimGraph
            graph={graph}
            onSelectNode={
              setSelectedNode
            }
          />
        </section>


        <NodeInspector
          node={selectedNode}
        />
      </main>
    </div>
  );
}
