import {
  useEffect,
  useState,
} from "react";


import DetectorPanel from "./DetectorPanel";
import ModelSelector from "./ModelSelector";

import ClaimGraph from "./ClaimGraph";
import NodeInspector from "./NodeInspector";

import "./App.css";
import "./index.css";


function mergeGraphPatch(
  current,
  patch,
) {
  if (!current) {
    return current;
  }


  const nodes = new Map(
    current.nodes.map(
      (node) => [
        node.node_id,
        node,
      ]
    )
  );


  const edges = new Map(
    current.edges.map(
      (edge) => [
        edge.edge_id,
        edge,
      ]
    )
  );


  for (
    const node
    of patch.new_nodes ?? []
  ) {
    nodes.set(
      node.node_id,
      node,
    );
  }


  for (
    const edge
    of patch.new_edges ?? []
  ) {
    edges.set(
      edge.edge_id,
      edge,
    );
  }


  return {
    ...current,

    nodes: [
      ...nodes.values(),
    ],

    edges: [
      ...edges.values(),
    ],
  };
}


export default function App() {
  const [graph, setGraph] =
    useState(null);

  const [
    selectedNode,
    setSelectedNode,
  ] = useState(null);

  const [
    selectedCandidate,
    setSelectedCandidate,
  ] = useState(null);

  const [
    selectedTarget,
    setSelectedTarget,
  ] = useState(null);

  const [
    investigationRunning,
    setInvestigationRunning,
  ] = useState(false);


  const [
    researchRunning,
    setResearchRunning,
  ] = useState(false);

  const [
    researchError,
    setResearchError,
  ] = useState(null);

  const [
    startupError,
    setStartupError,
  ] = useState(null);

  const [
    investigationError,
    setInvestigationError,
  ] = useState(null);


  // ------------------------------------------------------
  // STARTUP FALLBACK
  //
  // This remains only so that the application has
  // something visible before a live anomaly is selected.
  //
  // Once INVESTIGATE is clicked, this graph is replaced
  // by one generated live by the selected model.
  // ------------------------------------------------------

  useEffect(() => {
    fetch(
      "/investigation_live_nvidia.json"
    )
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            "Could not load startup graph: "
            + `HTTP ${response.status}`
          );
        }

        return response.json();
      })
      .then(setGraph)
      .catch((err) => {
        console.error(err);

        setStartupError(
          err.message
        );
      });
  }, []);


  // ------------------------------------------------------
  // LIVE INVESTIGATION
  //
  // Real anomaly
  //   -> selected model target
  //   -> ClaimGraph backend
  //   -> LLM decomposition
  //   -> validated graph
  //   -> Cytoscape
  // ------------------------------------------------------

  async function investigateCandidate(
    candidate,
  ) {
    if (!selectedTarget) {
      setInvestigationError(
        "No decomposition model selected."
      );

      return;
    }


    setSelectedCandidate(
      candidate
    );

    setSelectedNode(null);

    setInvestigationError(null);

    setInvestigationRunning(
      true
    );


    const pair =
      candidate.pair
      ?? (
        candidate.ticker_a
        && candidate.ticker_b
          ? (
              `${candidate.ticker_a}`
              + "/"
              + `${candidate.ticker_b}`
            )
          : ""
      );


    const [
      tickerA,
      tickerB,
    ] = pair.split("/");


    if (
      !tickerA
      || !tickerB
    ) {
      setInvestigationRunning(
        false
      );

      setInvestigationError(
        "Candidate does not contain "
        + "a valid ticker pair."
      );

      return;
    }


    const cointegrationP =
      candidate.cointegration_p
      ?? candidate.pvalue
      ?? candidate.p_value;


    const signalDate =
      candidate.signal_date
      ?? candidate.as_of
      ?? "2026-09-18";


    try {
      const response =
        await fetch(
          "/api/investigations/build",
          {
            method: "POST",

            headers: {
              "Content-Type":
                "application/json",
            },

            body: JSON.stringify({
              target_id:
                selectedTarget,

              ticker_a:
                tickerA,

              ticker_b:
                tickerB,

              signal_date:
                signalDate,

              z_score:
                candidate.z_score,

              correlation:
                candidate.correlation,

              cointegration_p:
                cointegrationP,
            }),
          },
        );


      const payload =
        await response.json();


      if (!response.ok) {
        throw new Error(
          payload.detail
          ?? payload.error
          ?? `HTTP ${response.status}`
        );
      }


      // This is the key integration boundary.
      //
      // The static startup graph disappears here and
      // Cytoscape receives the real model-generated
      // ClaimGraph.
      setGraph(
        payload
      );
    }
    catch (err) {
      console.error(err);

      setInvestigationError(
        `Investigation failed: ${
          err.message ?? String(err)
        }`
      );
    }
    finally {
      setInvestigationRunning(
        false
      );
    }
  }


  async function researchNode(
    node,
  ) {
    if (!selectedTarget) {
      setResearchError(
        "No model target selected."
      );

      return;
    }


    if (!graph?.pair) {
      setResearchError(
        "Research requires a live "
        + "anomaly investigation."
      );

      return;
    }


    const asOf =
      graph.as_of
      ?? selectedCandidate?.signal_date
      ?? selectedCandidate?.as_of;


    if (!asOf) {
      setResearchError(
        "Investigation has no historical "
        + "cutoff date."
      );

      return;
    }


    setResearchRunning(true);
    setResearchError(null);


    try {
      const response =
        await fetch(
          "/api/research/node",
          {
            method: "POST",

            headers: {
              "Content-Type":
                "application/json",
            },

            body: JSON.stringify({
              target_id:
                selectedTarget,

              pair:
                graph.pair,

              as_of:
                asOf,

              node: {
                node_id:
                  node.node_id,

                kind:
                  node.kind,

                label:
                  node.label,
              },
            }),
          },
        );


      const payload =
        await response.json();


      if (!response.ok) {
        throw new Error(
          payload.detail
          ?? payload.error
          ?? `HTTP ${response.status}`
        );
      }


      /*
       * Research extends the existing graph.
       *
       * It does NOT replace the original
       * investigation.
       */
      setGraph(
        (current) =>
          mergeGraphPatch(
            current,
            payload,
          )
      );
    }
    catch (err) {
      console.error(err);

      setResearchError(
        `Research failed: ${
          err.message
          ?? String(err)
        }`
      );
    }
    finally {
      setResearchRunning(false);
    }
  }


  if (startupError) {
    return (
      <div className="app-shell">
        <h1>ClaimGraph</h1>

        <p>
          Failed to load startup graph:
          {" "}
          {startupError}
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


  const anomaly =
    graph.nodes.find(
      (node) =>
        node.kind === "anomaly"
    );


  const displayTicker =
    graph.pair
    ?? graph.ticker
    ?? "—";


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
          <span>
            Pair
          </span>

          <strong>
            {displayTicker}
          </strong>

          <small>
            schema{" "}
            {graph.schema_version}
          </small>
        </div>
      </header>


      <ModelSelector
        value={selectedTarget}
        onChange={setSelectedTarget}
      />


      <section className="claim-summary">

        <div
          className="claim-summary__label"
        >
          Attention event
        </div>

        <div
          className="claim-summary__text"
        >
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


      {investigationRunning && (
        <div
          className="investigation-running"
        >
          GENERATING INVESTIGATION
          {" · "}
          {selectedCandidate?.pair
            ?? ""}
        </div>
      )}


      {investigationError && (
        <div
          className="investigation-error"
        >
          {investigationError}
        </div>
      )}


      <main className="workspace">

        <section className="graph-panel">

          <div className="panel-header">
            <div>
              <h2>
                Investigation graph
              </h2>

              <p>
                Inspect calculations,
                hypotheses, evidence
                requirements, assumptions
                and execution provenance.
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


          <DetectorPanel
            onSelectCandidate={
              investigateCandidate
            }
          />


          {selectedCandidate && (
            <div
              className="selected-candidate"
            >
              Investigating{" "}

              <strong>
                {selectedCandidate.pair}
              </strong>

              {" · "}
              z{" "}

              {Number(
                selectedCandidate.z_score
              ).toFixed(2)}
            </div>
          )}


          <ClaimGraph
            graph={graph}

            onSelectItem={
              setSelectedNode
            }
          />

        </section>


        <NodeInspector
          node={selectedNode}

          onResearch={
            researchNode
          }

          researchRunning={
            researchRunning
          }

          researchError={
            researchError
          }
        />

      </main>

    </div>
  );
}
