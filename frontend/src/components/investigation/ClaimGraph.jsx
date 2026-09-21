import { useEffect, useMemo, useState } from "react";

import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  applyNodeChanges,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";

import {
  evidenceRoles,
  filterGraph,
  itemKey,
  labelFor,
} from "../../lib/claimgraph/reviewModel.js";
import {
  temporalStatuses,
  temporalView,
} from "../../lib/claimgraph/temporalModel.js";
import {
  kindLabel,
  quarterlyView,
  toReactFlowEdges,
  toReactFlowNodes,
} from "./graphAdapter";

const STATUS_LABEL = {
  available_at_cutoff: "public at cutoff",
  derived_from_available_evidence: "derived from public evidence",
  appeared_after_cutoff: "after cutoff",
  date_unknown: "undated",
  hindsight_outcome: "hindsight",
};

function EvidenceNode({ data }) {
  return (
    <>
      <Handle type="target" position={Position.Top} />
      <div className="cg-node__kind">{data.displayKind}</div>
      <div className="cg-node__label">{data.label}</div>
      <div className="cg-node__tags">
        {STATUS_LABEL[data.temporalStatus] && (
          <span>{STATUS_LABEL[data.temporalStatus]}</span>
        )}
        {data.support && <span className="cg-tag--support">supports</span>}
        {data.counter && <span className="cg-tag--counter">counters</span>}
        {data.humanState && (
          <span className="cg-tag--human">{labelFor(data.humanState)}</span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </>
  );
}

const NODE_TYPES = { evidence: EvidenceNode };

function savedLayout(key) {
  try {
    return new Map(
      (JSON.parse(localStorage.getItem(key)) ?? []).map((node) => [node.id, node])
    );
  } catch {
    return new Map();
  }
}

/**
 * The canvas of one investigation.
 *
 * What is drawn is a VIEW of the graph: cut at an evidence
 * cutoff, narrowed by kind or role, or reduced to what one
 * follow-up added. The graph itself is never edited here,
 * and hidden nodes keep their place so a filter can be
 * lifted without the layout jumping.
 */
export default function ClaimGraph({
  graph,
  layoutKey,
  colorMode = "light",
  cutoff = "latest",
  filters = [],
  onFilters,
  delta = null,
  onlyNew = false,
  itemReviews = {},
  fitRequest = 0,
  visible = true,
  onSelectItem,
}) {
  const storageKey = `pythia:graph-layout:${layoutKey}`;

  const [flow, setFlow] = useState(null);
  const [showAtomic, setShowAtomic] = useState(false);
  const [showOlder, setShowOlder] = useState(false);
  const [expanded, setExpanded] = useState([]);

  const [moved, setMoved] = useState(() => savedLayout(storageKey));

  useEffect(() => {
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify(
          [...moved.values()].map(({ id, position }) => ({ id, position }))
        )
      );
    } catch {
      // Positions are a convenience; the graph is on the server.
    }
  }, [moved, storageKey]);

  const view = useMemo(() => temporalView(graph, cutoff), [graph, cutoff]);
  const statuses = useMemo(() => temporalStatuses(graph, cutoff), [graph, cutoff]);
  const roles = useMemo(() => evidenceRoles(view), [view]);

  const shown = useMemo(
    () => filterGraph(quarterlyView(view, { showAtomic, showOlder, expanded }), filters),
    [view, showAtomic, showOlder, expanded, filters]
  );

  const shownCount = onlyNew && delta ? -1 : shown.nodes.length;

  // A canvas mounted while hidden measures zero by zero. Fit
  // again when it is shown, and whenever someone asks.
  useEffect(() => {
    if (!flow || !visible) return undefined;

    const frame = requestAnimationFrame(() => flow.fitView({ padding: 0.12 }));

    return () => cancelAnimationFrame(frame);
  }, [flow, visible, fitRequest, shownCount]);

  const { nodes, edges } = useMemo(() => {
    const added = new Set(delta?.added_node_ids ?? []);
    const addedEdges = new Set(delta?.added_edge_ids ?? []);
    const affected = new Set(delta?.reassessed_hypothesis_ids ?? []);

    const admissible = new Set(view.nodes.map((node) => node.node_id));

    const ids = new Set(
      (onlyNew && delta
        ? [...added, ...affected]
        : shown.nodes.map((node) => node.node_id)
      ).filter((id) => admissible.has(id))
    );

    // Lanes are laid out from what is shown, so a filter that
    // hides whole lanes closes the gap they would leave. A
    // node someone dragged stays where they put it.
    const compact = new Map(
      toReactFlowNodes(graph.nodes.filter((node) => ids.has(node.node_id))).map(
        (node) => [node.id, node.position]
      )
    );

    const flowNodes = toReactFlowNodes(graph.nodes).map((node) => ({
      ...node,
      type: "evidence",
      position:
        moved.get(node.id)?.position ?? compact.get(node.id) ?? node.position,
      hidden: !ids.has(node.id),
      className: [
        node.className,
        delta && added.has(node.id) && "cg-node--new",
        delta && affected.has(node.id) && "cg-node--affected",
        delta && !added.has(node.id) && !affected.has(node.id) && "cg-node--old",
        roles.counter.has(node.id) && "cg-node--counter",
      ]
        .filter(Boolean)
        .join(" "),
      data: {
        ...node.data,
        temporalStatus: statuses.get(node.id),
        support: roles.support.has(node.id),
        counter: roles.counter.has(node.id),
        humanState: itemReviews[itemKey(node.data)]?.status,
      },
    }));

    const flowEdges = toReactFlowEdges(graph.edges).map((edge) => ({
      ...edge,
      hidden:
        !ids.has(edge.source) ||
        !ids.has(edge.target) ||
        (onlyNew && delta != null && !addedEdges.has(edge.id)),
      className: `${edge.className}${addedEdges.has(edge.id) ? " cg-edge--new" : ""}`,
    }));

    return { nodes: flowNodes, edges: flowEdges };
  }, [graph, view, shown, statuses, roles, delta, onlyNew, moved, itemReviews]);

  const kinds = useMemo(
    () => [...new Set(graph.nodes.map((node) => node.kind))],
    [graph]
  );

  const options = [
    ["support", "Supporting"],
    ["counter", "Countering"],
    ...kinds.map((kind) => [kind, kindLabel(kind)]),
  ];

  const hasQuarters = graph.nodes.some(
    (node) => node.data?.subtype === "fundamental_snapshot"
  );

  const toggle = (value) =>
    onFilters?.(
      filters.includes(value)
        ? filters.filter((item) => item !== value)
        : [...filters, value]
    );

  return (
    <div className="graph-container">
      <div className="graph-filters">
        <button
          className={`graph-filters__chip ${filters.length === 0 ? "is-active" : ""}`}
          onClick={() => onFilters?.([])}
        >
          All
        </button>

        {options.map(([value, label]) => (
          <button
            key={value}
            className={`graph-filters__chip ${filters.includes(value) ? "is-active" : ""}`}
            onClick={() => toggle(value)}
          >
            {label}
          </button>
        ))}

        {hasQuarters && (
          <>
            <span className="graph-filters__rule" />
            <button
              className={`graph-filters__chip ${showAtomic ? "is-active" : ""}`}
              title="Every SEC fact and filing behind the quarterly figures"
              onClick={() => setShowAtomic((value) => !value)}
            >
              SEC detail
            </button>
            <button
              className={`graph-filters__chip ${showOlder ? "is-active" : ""}`}
              onClick={() => setShowOlder((value) => !value)}
            >
              Older quarters
            </button>
          </>
        )}

        <span className="graph-filters__count mono">
          {shown.nodes.length}/{graph.nodes.length} nodes
        </span>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        colorMode={colorMode}
        onInit={setFlow}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.08}
        maxZoom={1.8}
        onNodesChange={(changes) =>
          setMoved((current) => {
            const dragged = changes.filter(
              (change) => change.type === "position" && change.position
            );

            if (dragged.length === 0) return current;

            const next = new Map(current);

            applyNodeChanges(dragged, nodes).forEach((node) => {
              if (dragged.some((change) => change.id === node.id)) {
                next.set(node.id, { id: node.id, position: node.position });
              }
            });

            return next;
          })
        }
        onNodeClick={(_, node) => {
          onSelectItem?.(node.data);

          // A quarter opens and closes its own SEC lineage.
          if (node.data.data?.subtype === "fundamental_snapshot") {
            setExpanded((current) =>
              current.includes(node.id)
                ? current.filter((id) => id !== node.id)
                : [...current, node.id]
            );
          }
        }}
        onEdgeClick={(_, edge) => onSelectItem?.(edge.data)}
      >
        <Background />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}
