import { ChevronIcon } from "../icons";
import { usePopover } from "./Popover";

/**
 * Which model explains the next anomaly. One investigation is
 * read by one model; choosing another and explaining again is
 * how two readings end up side by side in Why.
 */
export default function ModelMenu({ llm, models, modelId, onSelect }) {
  const [root, open, setOpen] = usePopover();
  const list = models?.models.filter((model) => model.roles.includes("analysis"));

  if (!list?.length) {
    return (
      <div className="topbar__model" title={llm?.detail}>
        <span className={`dot ${llm?.online ? "dot--on" : "dot--off"}`} />
        <span className="mono">MODEL</span>
      </div>
    );
  }

  const active = list.find((model) => model.id === modelId) ?? list[0];

  return (
    <div className="menu" ref={root}>
      <button
        type="button"
        className={`topbar__model menu__button ${open ? "is-open" : ""}`}
        title={`${active.model} · ${active.local ? "prompts stay on this machine" : "external endpoint"} · ${active.detail}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className={`dot ${active.online ? "dot--on" : "dot--off"}`} />
        <span className="mono menu__label">{active.label.toUpperCase()}</span>
        <span className="menu__chevron"><ChevronIcon size={14} /></span>
      </button>

      {open && (
        <div className="menu__panel" role="listbox" aria-label="Model">
          <div className="menu__heading eyebrow">Reads the next explanation</div>

          {list.map((model) => (
            <button
              key={model.id}
              type="button"
              role="option"
              aria-selected={model.id === active.id}
              className={`menu__item ${model.id === active.id ? "is-active" : ""}`}
              disabled={!model.online}
              title={model.detail}
              onClick={() => {
                onSelect(model.id);
                setOpen(false);
              }}
            >
              <span className={`dot ${model.online ? "dot--on" : "dot--off"}`} />
              <span className="menu__text">
                <span className="mono menu__name">{model.label.toUpperCase()}</span>
                <span className="menu__detail">
                  {model.online ? (model.local ? "on this machine" : "external endpoint") : "offline"}
                </span>
              </span>
              {model.id === active.id && <span className="menu__check mono">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
