import { useMemo, useState } from "react";

import { dateTime, shortDate } from "../../lib/format";
import { eventColor, eventLabel, radialLayout } from "../../lib/wire";

const WIDTH = 900;
const HEIGHT = 640;

function short(label, max = 26) {
  return label.length > max ? `${label.slice(0, max - 1)}…` : label;
}

/**
 * The security at the centre, what it was connected with on
 * the rings, time running clockwise. Solid edges happened;
 * their opacity is how expected they were. Dashed red edges
 * are what the model expects next.
 */
export default function WireGraph({ ticker, holdings, graph, loading, error, onSelectTicker }) {
  const [picked, setPicked] = useState(null);

  const layout = useMemo(() => (graph ? radialLayout(graph, { width: WIDTH, height: HEIGHT }) : null), [graph]);

  if (error) return <div className="error-banner">{error}</div>;
  if (loading && !graph) return <div className="empty"><span className="spinner" /> Laying out {ticker}…</div>;
  if (!graph || !layout) return null;

  const nodes = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
  const pickedEdges = picked ? graph.edges.filter((e) => e.dst === picked || e.src === picked) : [];
  const pickedNode = picked ? nodes[picked] : null;

  return (
    <div className="wiregraph">
      <div className="wiregraph__side">
        <div className="seg seg--wrap">
          {(holdings ?? []).map((h) => (
            <button key={h.ticker} className={`seg__item mono ${h.ticker === ticker ? "is-active" : ""}`} onClick={() => onSelectTicker(h.ticker)}>
              {h.ticker}
            </button>
          ))}
        </div>

        <p className="muted">
          {graph.edges.length} edges, {shortDate(graph.start)} → {shortDate(graph.end)}.
          {graph.predictions.length > 0 && ` ${graph.predictions.length} expected next, as of ${shortDate(graph.predictions[0].as_of)}.`}
        </p>

        <ul className="legend">
          <li><span className="legend__line" /> happened · lighter = expected</li>
          <li><span className="legend__line legend__line--predicted" /> expected next (model)</li>
          <li><span className="legend__dot" style={{ background: "var(--accent)" }} /> event type</li>
          <li><span className="legend__dot" style={{ background: "var(--text)" }} /> event · entity</li>
        </ul>

        {pickedNode ? (
          <div className="wiregraph__pick">
            <span className="eyebrow">{pickedNode.kind.replace("_", " ")}</span>
            <h3>{pickedNode.label}</h3>
            {pickedNode.kind === "security" && pickedNode.label !== ticker && (
              <button className="btn btn--ghost btn--small" onClick={() => onSelectTicker(pickedNode.label)}>
                Open {pickedNode.label}
              </button>
            )}
            <ul className="wiregraph__articles">
              {pickedEdges.map((e) => (
                <li key={e.id}>
                  <span className="event__type" style={{ "--event": eventColor(e.event_type) }}>{eventLabel(e.event_type)}</span>
                  {e.article ? (
                    <a href={e.article.url} target="_blank" rel="noreferrer">{e.article.title}</a>
                  ) : (
                    <span>{e.kind}</span>
                  )}
                  <span className="muted mono">
                    {dateTime(e.t)}
                    {e.prob != null && ` · surprise ${(1 - e.prob).toFixed(2)}`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="muted">Click a node to see the articles behind its edges.</p>
        )}
      </div>

      <svg className="wiregraph__canvas" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`News graph of ${ticker}`}>
        <circle cx={layout.centre.x} cy={layout.centre.y} r={layout.radius} className="wiregraph__ring" />
        <circle cx={layout.centre.x} cy={layout.centre.y} r={layout.radius * 0.42} className="wiregraph__ring" />

        {graph.edges.map((e) => {
          const a = layout.positions[e.src];
          const b = layout.positions[e.dst];
          if (!a || !b) return null;
          const surprise = e.prob == null ? 0.5 : 1 - e.prob;
          const dim = picked && e.src !== picked && e.dst !== picked;

          return (
            <line
              key={e.id}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              className="wiregraph__edge"
              style={{ stroke: eventColor(e.event_type), opacity: dim ? 0.06 : 0.15 + surprise * 0.75, strokeWidth: 0.6 + surprise * 1.6 }}
            />
          );
        })}

        {graph.predictions.map((p) => {
          const a = layout.positions[layout.securityId];
          const b = layout.positions[p.dst];
          if (!a || !b) return null;

          return (
            <line
              key={`p:${p.dst}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              className="wiregraph__edge wiregraph__edge--predicted"
              style={{ opacity: 0.35 + p.prob * 0.6 }}
            >
              <title>expected next · p={p.prob.toFixed(2)}</title>
            </line>
          );
        })}

        {graph.nodes.map((n) => {
          const p = layout.positions[n.id];
          if (!p) return null;
          const isCentre = n.id === layout.securityId;
          const isHub = n.kind === "event_type";
          const r = isCentre ? 22 : isHub ? 9 : n.kind === "security" ? 8 : 4.5;

          return (
            <g key={n.id} className={`wiregraph__node ${picked === n.id ? "is-picked" : ""}`} transform={`translate(${p.x},${p.y})`} onClick={() => setPicked(picked === n.id ? null : n.id)}>
              <circle r={r} className={`wiregraph__dot wiregraph__dot--${n.kind}`} style={isHub ? { fill: eventColor(n.label) } : undefined} />
              <text
                className={`wiregraph__label mono ${isCentre ? "is-centre" : ""}`}
                dy={isCentre ? 4 : -r - 4}
                textAnchor="middle"
              >
                {isCentre ? n.label : isHub ? eventLabel(n.label) : short(n.label)}
              </text>
              <title>{n.label}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
