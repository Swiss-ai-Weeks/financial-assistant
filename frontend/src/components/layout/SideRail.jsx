import { CloverIcon, GraphIcon, PastIcon, ScopeIcon } from "../icons";

/*
 * The three stories are one loop, read as a timeline:
 * what I missed, what I am looking at, what to look at next.
 */
const VIEWS = [
  { key: "postmortem", label: "Past", title: "Post-mortem: what did I miss?", icon: PastIcon },
  { key: "copilot", label: "Now", title: "Copilot: what is happening to this stock?", icon: ScopeIcon },
  { key: "discovery", label: "Next", title: "Discovery: what should I look at?", icon: CloverIcon },
  { key: "graph", label: "Why", title: "ClaimGraph: why are these connected?", icon: GraphIcon, divider: true },
];

export default function SideRail({ view, onChange }) {
  return (
    <nav className="rail">
      {VIEWS.map(({ key, label, title, icon: Glyph, divider }) => (
        <button
          key={key}
          title={title}
          aria-label={title}
          className={`rail__item ${view === key ? "is-active" : ""} ${
            divider ? "rail__item--divided" : ""
          }`}
          onClick={() => onChange(key)}
        >
          <Glyph />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
