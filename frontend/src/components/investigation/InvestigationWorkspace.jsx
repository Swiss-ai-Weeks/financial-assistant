import { useCallback, useMemo, useState } from "react";

import { api } from "../../api/client";
import { isActive, useInvestigation } from "../../hooks/useInvestigation";
import { usePersistentState } from "../../hooks/usePersistentState";
import {
  applyCopilotAction,
  buildCopilotViewContext,
} from "../../lib/claimgraph/copilotContext.js";
import {
  createReview,
  itemKey,
  restoreReview,
  serializeReview,
  updateReview,
} from "../../lib/claimgraph/reviewModel.js";
import {
  originalCutoff,
  temporalView,
} from "../../lib/claimgraph/temporalModel.js";
import { turnOverlay } from "../../lib/claimgraph/turns.js";
import { dateTime } from "../../lib/format";
import ClaimGraph from "./ClaimGraph";
import CopilotPanel from "./CopilotPanel";
import NodeInspector from "./NodeInspector";
import ReportPanel from "./ReportPanel";
import ReviewPanel from "./ReviewPanel";
import StageList from "./StageList";
import TemporalBar from "./TemporalBar";

const DEFAULT_FILTERS = [
  "anomaly",
  "hypothesis",
  "claim",
  "calculation",
  "inference",
  "missing_evidence",
  "evidence_requirement",
];

const reviewKey = (graph) =>
  `pythia:review:${graph.investigation_id ?? graph.anomaly_id}`;

function loadReview(graph) {
  try {
    return restoreReview(graph, localStorage.getItem(reviewKey(graph)));
  } catch {
    return { review: createReview(graph), reason: "Kept in memory only." };
  }
}

function exportReview(graph, review) {
  const blob = new Blob(
    [JSON.stringify({ review, investigation: graph }, null, 2)],
    { type: "application/json" }
  );

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = `${review.review_id.replace(/[^a-z0-9_-]/gi, "_")}.json`;
  link.click();

  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * One investigation, opened as a tab.
 *
 * A tab stays mounted while another is shown, and what was
 * being looked at (filters, evidence cutoff, selected node,
 * which follow-up) is remembered per investigation, so
 * switching between two models' graphs of the same anomaly
 * is immediate and loses nothing.
 */
export default function InvestigationWorkspace({
  tab,
  visible,
  theme,
  models,
  onSettled,
}) {
  const [fetched, refresh] = useInvestigation(
    tab.example ? null : tab.id,
    onSettled
  );

  const run = tab.example ? tab.run : fetched;

  if (!run) {
    return <div className="empty">Opening the investigation…</div>;
  }

  if (!run.graph) {
    return (
      <div className="workspace workspace--pending">
        <span className="eyebrow">
          {run.model_label || run.model} · {run.status}
        </span>
        <h2>{run.anomaly.summary}</h2>
        <StageList stages={run.stages} />
        {run.error && <div className="error-banner">{run.error}</div>}
      </div>
    );
  }

  return (
    <GraphWorkspace
      key={run.investigation_id}
      run={run}
      example={Boolean(tab.example)}
      visible={visible}
      theme={theme}
      models={models}
      onRefresh={refresh}
    />
  );
}

function GraphWorkspace({ run, example, visible, theme, models, onRefresh }) {
  const graph = run.graph;
  const id = run.investigation_id;

  const [ui, setUi] = usePersistentState(`workspace:${id}`, {
    filters: DEFAULT_FILTERS,
    cutoff: originalCutoff(graph) ?? "latest",
    turn: null,
    onlyNew: false,
    panel: "graph",
    selected: null,
  });

  const patch = useCallback(
    (change) => setUi((current) => ({ ...current, ...change })),
    [setUi]
  );

  const [initial] = useState(() => loadReview(graph));
  const [review, setReview] = useState(initial.review);
  const [persistence, setPersistence] = useState(initial.reason);

  const [fitRequest, setFitRequest] = useState(0);
  const [followUpError, setFollowUpError] = useState(null);
  const [starting, setStarting] = useState(false);

  const saveReview = (next) => {
    setReview(next);

    try {
      localStorage.setItem(reviewKey(graph), serializeReview(graph, next));
      setPersistence("Stored in this browser; export to keep a copy.");
    } catch {
      setPersistence("Browser storage is unavailable; export to keep a copy.");
    }
  };

  const onReviewChange = (change) =>
    saveReview({
      ...review,
      ...change,
      // Editing an approved case reopens it.
      status: review.status === "approved" ? "needs_review" : review.status,
      updated_at: new Date().toISOString(),
    });

  // Throws when the reviewer or the rationale is missing; the
  // action form shows the message.
  const onReviewAction = (action) => saveReview(updateReview(review, action));

  const cutoff = ui.cutoff;
  const inspected = useMemo(() => temporalView(graph, cutoff), [graph, cutoff]);

  const latestTurn = graph.followups?.at(-1)?.run_id ?? null;
  const delta = turnOverlay(graph, ui.turn);

  const selected = useMemo(() => {
    if (!ui.selected) return null;

    if (ui.selected.edge) {
      const edge = graph.edges.find((item) => item.edge_id === ui.selected.id);

      return edge
        ? { ...edge, ...edge.data, inspectorType: "edge", label: edge.kind.replaceAll("_", " ") }
        : null;
    }

    const node = graph.nodes.find((item) => item.node_id === ui.selected.id);

    return node ? { ...node, inspectorType: "node" } : null;
  }, [graph, ui.selected]);

  const select = useCallback(
    (item) =>
      patch({
        selected: item
          ? { id: item.edge_id ?? item.node_id, edge: item.inspectorType === "edge" }
          : null,
      }),
    [patch]
  );

  const running = isActive(run);

  const model = models?.models.find((item) => item.id === run.model_id);

  const followUp = example
    ? { disabled: true, reason: "Saved example: open a live investigation to research it." }
    : {
        disabled: running || starting || (model != null && !model.online),
        running: running || starting,
        reason: running
          ? "A follow-up is already running"
          : model != null && !model.online
            ? `${model.label} is offline (${model.detail})`
            : undefined,
        start: async (requirementId) => {
          setStarting(true);
          setFollowUpError(null);

          try {
            await api.startFollowUp(id, requirementId, run.model_id);
            onRefresh();
          } catch (error) {
            setFollowUpError(error.message);
          } finally {
            setStarting(false);
          }
        },
      };

  const activeFollowUp = (run.followups ?? []).find((item) =>
    ["queued", "running"].includes(item.status)
  );

  const lastFollowUp = run.followups?.at(-1);

  const buildContext = () =>
    buildCopilotViewContext({
      graph,
      workspaceId: id,
      model: { label: run.model_label || run.model },
      selected,
      cutoff,
      filters: ui.filters,
      onlyNew: ui.onlyNew,
    });

  const onCopilotAction = (action) =>
    applyCopilotAction(action, inspected, {
      select,
      filters: (value) => patch({ filters: value, onlyNew: false, turn: null, panel: "graph" }),
      fit: () => {
        patch({ panel: "graph" });
        setFitRequest((value) => value + 1);
      },
    });

  return (
    <div className="workspace">
      <header className="workspace__header">
        <div className="workspace__title">
          <span className="eyebrow">
            ClaimGraph · {run.model_label || run.model.split("/").pop()}
            {run.model_local != null && (run.model_local ? " · local" : " · external")}
            {example && " · saved example"}
          </span>
          <h2>{run.anomaly.summary}</h2>
        </div>

        <div className="workspace__meta mono">
          <span>cutoff {dateTime(run.evidence_cutoff)} UTC</span>
          <span>
            {graph.nodes.length} nodes · {graph.edges.length} edges
          </span>
          {run.usage?.calls > 0 && (
            <span>
              {run.usage.calls} model calls
              {run.usage.completion_tokens > 0 &&
                ` · ${run.usage.completion_tokens.toLocaleString()} tokens out`}
            </span>
          )}
        </div>
      </header>

      <div className="workspace__toolbar">
        <div className="workspace__panels">
          {[
            ["graph", "Evidence graph"],
            ["review", "Review"],
            ["report", "Report"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={`tabs__tab ${ui.panel === key ? "is-active" : ""}`}
              onClick={() => patch({ panel: key })}
            >
              {label}
            </button>
          ))}
        </div>

        {(graph.followups?.length ?? 0) > 0 && (
          <label className="workspace__turn">
            <span className="eyebrow">Turn</span>
            <select
              value={ui.turn ?? ""}
              onChange={(event) =>
                patch({ turn: event.target.value || null, onlyNew: false })
              }
            >
              <option value="">Whole graph</option>
              <option value="initial">Initial investigation</option>
              {graph.followups.map((item, index) => (
                <option key={item.run_id} value={item.run_id}>
                  Follow-up {index + 1}
                </option>
              ))}
            </select>
          </label>
        )}

        <button
          className="btn btn--ghost btn--small"
          onClick={() => setFitRequest((value) => value + 1)}
        >
          Fit
        </button>
      </div>

      <TemporalBar
        graph={graph}
        cutoff={cutoff}
        onChange={(value) => patch({ cutoff: value })}
        onSelect={select}
      />

      {followUpError && <div className="error-banner">{followUpError}</div>}

      {activeFollowUp && (
        <div className="workspace__followup">
          <span className="eyebrow">Researching · {activeFollowUp.question}</span>
          <StageList stages={activeFollowUp.stages} />
        </div>
      )}

      {!activeFollowUp && lastFollowUp && lastFollowUp.run_id === latestTurn && (
        <div className="workspace__followup workspace__followup--done">
          <span className="eyebrow">
            Follow-up · {String(lastFollowUp.resolution ?? lastFollowUp.status).replaceAll("_", " ")}
          </span>
          <p>
            <strong>{lastFollowUp.question}</strong> {lastFollowUp.summary}
          </p>
          <div className="workspace__followup-actions">
            <span className="muted mono">
              +{lastFollowUp.added_nodes} nodes · +{lastFollowUp.added_edges} edges
            </span>
            <button
              className="btn btn--ghost btn--small"
              onClick={() => patch({ turn: lastFollowUp.run_id, onlyNew: true, panel: "graph" })}
            >
              Show only what it found
            </button>
            <button
              className="btn btn--ghost btn--small"
              onClick={() => patch({ turn: lastFollowUp.run_id, onlyNew: false, panel: "graph" })}
            >
              Show in context
            </button>
            {ui.turn && (
              <button
                className="btn btn--ghost btn--small"
                onClick={() => patch({ turn: null, onlyNew: false })}
              >
                Whole graph
              </button>
            )}
          </div>
          {lastFollowUp.error && <div className="error-banner">{lastFollowUp.error}</div>}
        </div>
      )}

      <div className={`workspace__body ${selected ? "has-inspector" : ""}`}>
        <div className="workspace__main">
          {/* The canvas stays mounted behind the other panels:
              its layout and zoom survive a look at the report. */}
          <div className="workspace__canvas" hidden={ui.panel !== "graph"}>
            <ClaimGraph
              graph={graph}
              layoutKey={id}
              colorMode={theme}
              cutoff={cutoff}
              filters={ui.filters}
              onFilters={(value) => patch({ filters: value })}
              delta={delta}
              onlyNew={ui.onlyNew}
              itemReviews={review.item_reviews}
              fitRequest={fitRequest}
              visible={visible && ui.panel === "graph"}
              onSelectItem={select}
            />
          </div>

          {ui.panel === "review" && (
            <ReviewPanel
              graph={inspected}
              review={review}
              persistence={persistence}
              onChange={onReviewChange}
              onAction={onReviewAction}
              onSelect={select}
              onExport={() => exportReview(graph, review)}
            />
          )}

          {ui.panel === "report" && (
            <ReportPanel
              graph={graph}
              cutoff={cutoff === "latest" ? originalCutoff(graph) : cutoff}
              workspaceId={id}
              reportMode={ui.reportMode ?? "existing_position"}
              onReportModeChange={(reportMode) => patch({ reportMode })}
              onClose={() => patch({ panel: "graph" })}
              onSelect={select}
            />
          )}

          <CopilotPanel
            buildContext={buildContext}
            graph={graph}
            modelId={run.model_id}
            modelLabel={run.model_label}
            followUp={followUp}
            onAction={onCopilotAction}
          />
        </div>

        {selected && (
          <NodeInspector
            key={itemKey(selected)}
            node={selected}
            graph={graph}
            cutoff={cutoff}
            reviewState={review.item_reviews[itemKey(selected)]}
            followUp={followUp}
            onSelect={select}
            onAction={onReviewAction}
            onClose={() => select(null)}
          />
        )}
      </div>
    </div>
  );
}
