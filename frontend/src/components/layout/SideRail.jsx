import { ChartIcon, ChipIcon, GraphIcon } from "../icons";

const VIEWS = [
  { key: "desk", label: "Desk", icon: ChartIcon },
  { key: "graph", label: "ClaimGraph", icon: GraphIcon },
  { key: "model", label: "Model", icon: ChipIcon },
];

export default function SideRail({ view, onChange }) {
  return (
    <nav className="rail">
      {VIEWS.map(({ key, label, icon: Glyph }) => (
        <button
          key={key}
          title={label}
          aria-label={label}
          className={`rail__item ${view === key ? "is-active" : ""}`}
          onClick={() => onChange(key)}
        >
          <Glyph />
        </button>
      ))}
    </nav>
  );
}
