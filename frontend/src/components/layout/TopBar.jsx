import { compact, money, percent, price, signed, tone } from "../../lib/format";
import { ClockIcon, MoonIcon, StarIcon, SunIcon } from "../icons";
import TickerSearch from "../portfolio/TickerSearch";

function Stat({ label, value, className = "" }) {
  return (
    <div className="stat">
      <div className="stat__label">{label}</div>
      <div className={`stat__value mono ${className}`}>{value}</div>
    </div>
  );
}

/**
 * Which model explains the next anomaly. One investigation is
 * read by one model; choosing another and explaining again
 * is how two readings end up side by side in Why.
 */
function ModelPicker({ llm, models, modelId, onSelect }) {
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
    <label
      className="topbar__model"
      title={`${active.model} · ${active.local ? "prompts stay on this machine" : "external endpoint"} · ${active.detail}`}
    >
      <span className={`dot ${active.online ? "dot--on" : "dot--off"}`} />
      <select
        className="mono"
        value={active.id}
        onChange={(event) => onSelect(event.target.value)}
      >
        {list.map((model) => (
          <option key={model.id} value={model.id}>
            {model.label.toUpperCase()}
            {model.online ? "" : " · OFFLINE"}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function TopBar({
  ticker,
  quote,
  portfolio,
  llm,
  models,
  modelId,
  asOf,
  latestSession,
  theme,
  onSelectModel,
  onTimeTravel,
  onToggleTheme,
  onSelectTicker,
  onAddTicker,
  onRemoveTicker,
}) {
  const holdings = portfolio?.positions ?? [];
  const held = holdings.some((position) => position.ticker === ticker);

  return (
    <header className="topbar">
      <div className="logo mono" aria-label="Pythia">
        <span>PY</span>
        <span>TH</span>
      </div>

      <div className="topbar__instrument">
        <button
          className={`topbar__star ${held ? "is-held" : ""}`}
          title={held ? "Remove from the book" : "Add to the book"}
          onClick={() => (held ? onRemoveTicker(ticker) : onAddTicker(ticker))}
        >
          <StarIcon filled={held} />
        </button>

        <TickerSearch
          ticker={ticker}
          holdings={holdings}
          onSelect={onSelectTicker}
          onAdd={onAddTicker}
        />
      </div>

      <div className="topbar__price mono">
        <div className="topbar__last">{price(quote?.last)}</div>
        <div className="topbar__previous">{price(quote?.previous_close)}</div>
      </div>

      <div className="topbar__stats">
        <Stat label="1D CHG" value={signed(quote?.change)} className={tone(quote?.change)} />
        <Stat label="% CHG" value={percent(quote?.change_pct)} className={tone(quote?.change_pct)} />
        <Stat label="OPEN" value={price(quote?.open)} />
        <Stat label="LO" value={price(quote?.low)} />
        <Stat label="HI" value={price(quote?.high)} />
        <Stat label="VOL" value={compact(quote?.volume)} />
        <Stat label="1M RET" value={percent(quote?.month_return_pct)} className={tone(quote?.month_return_pct)} />
      </div>

      <div className="topbar__right">
        <div className="topbar__book">
          <div className="stat__label">BOOK VALUE</div>
          <div className="topbar__value mono">
            <small>$</small>
            {money(portfolio?.market_value)}
          </div>
        </div>

        {/* The whole desk moves: later prices and later news
            stop existing until it is brought back to today. */}
        <label
          className={`topbar__asof ${asOf ? "is-replay" : ""}`}
          title={
            asOf
              ? "Replay: nothing after this date exists for the desk"
              : "Live. Pick a past session to replay the desk as of that day"
          }
        >
          <ClockIcon size={16} />
          <span className="stat__label">{asOf ? "REPLAY" : "LIVE"}</span>
          <input
            type="date"
            className="mono"
            value={asOf ?? ""}
            max={latestSession ?? undefined}
            onChange={(event) => onTimeTravel(event.target.value || null)}
          />
          {asOf && (
            <button
              type="button"
              className="topbar__today mono"
              onClick={() => onTimeTravel(null)}
            >
              TODAY
            </button>
          )}
        </label>

        <ModelPicker
          llm={llm}
          models={models}
          modelId={modelId}
          onSelect={onSelectModel}
        />

        <button className="topbar__icon" onClick={onToggleTheme} title="Toggle theme">
          {theme === "light" ? <SunIcon /> : <MoonIcon />}
        </button>
      </div>
    </header>
  );
}
