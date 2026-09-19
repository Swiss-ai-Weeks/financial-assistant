import { compact, money, percent, price, signed, tone } from "../../lib/format";
import { MoonIcon, StarIcon, SunIcon } from "../icons";
import TickerSearch from "../portfolio/TickerSearch";

function Stat({ label, value, className = "" }) {
  return (
    <div className="stat">
      <div className="stat__label">{label}</div>
      <div className={`stat__value mono ${className}`}>{value}</div>
    </div>
  );
}

export default function TopBar({
  ticker,
  quote,
  portfolio,
  llm,
  theme,
  onToggleTheme,
  onSelectTicker,
  onAddTicker,
  onRemoveTicker,
  onOpenModel,
}) {
  const holdings = portfolio?.positions ?? [];
  const held = holdings.some((position) => position.ticker === ticker);

  return (
    <header className="topbar">
      <div className="logo mono" aria-label="ClaimGraph">
        <span>CL</span>
        <span>GR</span>
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

        <button className="topbar__model" onClick={onOpenModel} title={llm?.detail}>
          <span className={`dot ${llm?.online ? "dot--on" : "dot--off"}`} />
          <span className="mono">NEMOTRON</span>
        </button>

        <button className="topbar__icon" onClick={onToggleTheme} title="Toggle theme">
          {theme === "light" ? <SunIcon /> : <MoonIcon />}
        </button>
      </div>
    </header>
  );
}
