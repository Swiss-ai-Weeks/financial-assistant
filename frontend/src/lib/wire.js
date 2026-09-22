/** Presentation of the news graph: event types, colours, layout. */

export const EVENT_TYPES = {
  earnings: { label: "Earnings", hue: 32 },
  guidance: { label: "Guidance", hue: 45 },
  m_and_a: { label: "M&A", hue: 280 },
  regulation: { label: "Regulation", hue: 0 },
  litigation: { label: "Litigation", hue: 350 },
  supply_chain: { label: "Supply chain", hue: 200 },
  customer: { label: "Customer", hue: 160 },
  product: { label: "Product", hue: 220 },
  management: { label: "Management", hue: 300 },
  capital: { label: "Capital", hue: 90 },
  analyst: { label: "Analyst", hue: 60 },
  macro: { label: "Macro", hue: 190 },
  market_commentary: { label: "Commentary", hue: 0, muted: true },
  other: { label: "Other", hue: 0, muted: true },
};

export function eventLabel(type) {
  return EVENT_TYPES[type]?.label ?? type ?? "—";
}

export function eventColor(type) {
  const meta = EVENT_TYPES[type];

  if (!meta || meta.muted) return "var(--text-faint)";

  return `oklch(0.62 0.16 ${meta.hue})`;
}

/** 0..1 -> how surprising, in words a trader reads at a glance. */
export function surpriseWord(value) {
  if (value == null) return null;
  if (value >= 0.8) return "unexpected";
  if (value >= 0.6) return "unusual";

  return null;
}

/**
 * Radial layout of a security's neighbourhood. The security
 * sits at the centre; event-type hubs on an inner ring; events
 * and entities on the outer ring, ordered by when they were
 * last mentioned so time reads clockwise. Predicted-only nodes
 * (no observed edge yet) sit on a faint third ring.
 */
export function radialLayout(graph, { width, height }) {
  const centre = { x: width / 2, y: height / 2 };
  const radius = Math.min(width, height) / 2 - 60;
  const security = graph.nodes.find((n) => n.kind === "security" && n.label === graph.ticker);
  const observed = new Set(graph.edges.flatMap((e) => [e.src, e.dst]));

  const lastSeen = {};
  for (const edge of graph.edges) lastSeen[edge.dst] = edge.t;

  const positions = {};
  if (security) positions[security.id] = centre;

  const hubs = graph.nodes.filter((n) => n.kind === "event_type" && observed.has(n.id));
  hubs.forEach((node, index) => {
    const angle = (index / hubs.length) * Math.PI * 2 - Math.PI / 2;
    positions[node.id] = { x: centre.x + Math.cos(angle) * radius * 0.42, y: centre.y + Math.sin(angle) * radius * 0.42 };
  });

  const outer = graph.nodes
    .filter((n) => (n.kind === "event" || n.kind === "entity" || (n.kind === "security" && n.label !== graph.ticker)) && observed.has(n.id))
    .sort((a, b) => (lastSeen[a.id] ?? "").localeCompare(lastSeen[b.id] ?? ""));
  outer.forEach((node, index) => {
    const angle = (index / Math.max(outer.length, 1)) * Math.PI * 2 - Math.PI / 2;
    positions[node.id] = { x: centre.x + Math.cos(angle) * radius, y: centre.y + Math.sin(angle) * radius };
  });

  const expected = graph.nodes.filter((n) => !observed.has(n.id) && n.id !== security?.id);
  expected.forEach((node, index) => {
    const angle = (index / Math.max(expected.length, 1)) * Math.PI * 2 + Math.PI / 4;
    positions[node.id] = { x: centre.x + Math.cos(angle) * radius * 1.18, y: centre.y + Math.sin(angle) * radius * 1.18 };
  });

  return { positions, centre, radius, securityId: security?.id ?? null };
}
