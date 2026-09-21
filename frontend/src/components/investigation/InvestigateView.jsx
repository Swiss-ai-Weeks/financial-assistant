import { useState } from "react";

import CompareView from "./CompareView";
import InvestigationWorkspace from "./InvestigationWorkspace";

const EXAMPLES = [
  ["examples/investigation_temporal_demo.json", "Temporal replay · teaching case"],
  ["examples/investigation_review_demo.json", "Support, counter-evidence and gaps"],
  ["examples/investigation_live_nvidia.json", "NVDA · saved model run"],
];

/** A saved graph dressed as a run, so it opens like any other. */
function asRun(graph, label) {
  const anomaly = graph.nodes.find((node) => node.kind === "anomaly");

  return {
    investigation_id: graph.investigation_id ?? label,
    status: "completed",
    created_at: anomaly?.data?.detected_at ?? new Date().toISOString(),
    evidence_cutoff:
      anomaly?.data?.metadata?.observed_at ?? anomaly?.data?.detected_at,
    model: "saved example",
    model_label: "Saved example",
    anomaly: {
      anomaly_id: anomaly?.node_id ?? label,
      ticker: graph.ticker ?? "",
      related_tickers: [],
      summary: anomaly?.label ?? label,
    },
    stages: [],
    hypotheses: [],
    claims: [],
    followups: [],
    graph,
  };
}

/**
 * The "Why" view: every open ClaimGraph as a tab, next to the
 * comparison of what different models made of the same
 * anomaly.
 *
 * Tabs are mounted the first time they are shown and then
 * kept, hidden, while another one is in front. Coming back to
 * a graph is a CSS change, not a reload.
 */
export default function InvestigateView({
  tabs,
  active,
  visible,
  theme,
  investigations,
  models,
  focusAnomalyId,
  onActivate,
  onClose,
  onOpen,
  onOpenExample,
  onExplain,
  onSettled,
}) {
  // Once shown, a tab stays mounted.
  const [seen, setSeen] = useState(() => new Set([active]));

  if (!seen.has(active)) setSeen(new Set([...seen, active]));

  const [exampleError, setExampleError] = useState(null);

  const openExample = async (path, label) => {
    setExampleError(null);

    try {
      const response = await fetch(new URL(path, document.baseURI));

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      onOpenExample(asRun(await response.json(), label), label);
    } catch (error) {
      setExampleError(`Could not open the example: ${error.message}`);
    }
  };

  return (
    <div className="investigate">
      <nav className="investigate__tabs" aria-label="Open investigations">
        <button
          className={`investigate__tab ${active === "compare" ? "is-active" : ""}`}
          onClick={() => onActivate("compare")}
        >
          Compare models
        </button>

        {tabs.map((tab) => (
          <span
            key={tab.id}
            className={`investigate__tab ${active === tab.id ? "is-active" : ""}`}
          >
            <button onClick={() => onActivate(tab.id)} title={tab.title}>
              <strong className="mono">{tab.label}</strong>
              <small>{tab.model}</small>
            </button>
            <button
              className="investigate__close"
              aria-label={`Close ${tab.label}`}
              onClick={() => onClose(tab.id)}
            >
              ✕
            </button>
          </span>
        ))}

        <details className="investigate__examples">
          <summary>Saved examples</summary>
          <div>
            {EXAMPLES.map(([path, label]) => (
              <button key={path} className="link-button" onClick={() => openExample(path, label)}>
                {label}
              </button>
            ))}
            <p className="muted">
              Illustrative graphs that open without a model: inspect, review,
              travel in time, export a report.
            </p>
          </div>
        </details>
      </nav>

      {exampleError && <div className="error-banner">{exampleError}</div>}

      <div className="investigate__body">
        <div className="investigate__pane" hidden={active !== "compare"}>
          <CompareView
            investigations={investigations}
            models={models}
            focusAnomalyId={focusAnomalyId}
            onOpen={onOpen}
            onExplain={onExplain}
          />
        </div>

        {tabs
          .filter((tab) => seen.has(tab.id))
          .map((tab) => (
            <div key={tab.id} className="investigate__pane" hidden={active !== tab.id}>
              <InvestigationWorkspace
                tab={tab}
                visible={visible && active === tab.id}
                theme={theme}
                models={models}
                onSettled={onSettled}
              />
            </div>
          ))}
      </div>
    </div>
  );
}
