import { BookIcon, CloverIcon, GraphIcon, PastIcon, ScopeIcon, WireIcon } from "../icons";

/*
 * The three stories are one loop, read as a timeline:
 * what I missed, what I am looking at, what to look at next.
 */
const VIEWS = [
  { key: "postmortem", label: "Past", title: "Post-mortem: what did I miss?", icon: PastIcon },
  { key: "copilot", label: "Now", title: "Copilot: what is happening to this stock?", icon: ScopeIcon },
  { key: "discovery", label: "Next", title: "Discovery: what should I look at?", icon: CloverIcon },
  { key: "portfolio", label: "Book", title: "Portfolio: returns, risk, research and simulation", icon: BookIcon, divider: true },
  { key: "graph", label: "Why", title: "ClaimGraph: open investigations, side by side across models", icon: GraphIcon },
  { key: "wire", label: "Wire", title: "Wire: the news graph of the book and what the model did not expect", icon: WireIcon },
];

export default function SideRail({ view, onChange, badges = {} }) {
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
          {badges[key] > 0 && <em className="rail__badge mono">{badges[key]}</em>}
        </button>
      ))}
    </nav>
  );
}
