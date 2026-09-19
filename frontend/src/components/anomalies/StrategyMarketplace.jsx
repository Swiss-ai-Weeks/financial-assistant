import { StrategyIcon } from "../icons";
import PairScanResult from "./PairScanResult";

/**
 * The monitor marketplace.
 *
 * Every strategy rests on one assumption about the
 * market. Selecting a monitor shows where that
 * assumption broke, on the chart and in the blotter.
 */
export default function StrategyMarketplace({
  strategies,
  active,
  pairScan,
  onSelect,
  onSelectPair,
}) {
  return (
    <div className="market">
      <div className="market__header">
        <h2>Strategy Monitor Marketplace</h2>
        <p className="market__tagline mono">
          Choose a strategy, see where it broke, read why.
        </p>
      </div>

      {pairScan && <PairScanResult scan={pairScan} onSelectPair={onSelectPair} />}

      <div className="market__grid">
        {strategies.map((card) => {
          const selected = active === card.key;

          return (
            <article
              key={card.key}
              className={`card ${selected ? "is-selected" : ""}`}
            >
              <div className="card__top">
                <div className="card__icon" style={{ color: `var(--${card.key})` }}>
                  <StrategyIcon strategy={card.key} />
                </div>
                <div className="card__count mono" title="Anomalies in the review window">
                  {card.anomaly_count}
                </div>
              </div>

              <div className="eyebrow">{card.category}</div>
              <h3 className="card__name">{card.name}</h3>
              <p className="card__text">{card.description}</p>

              <dl className="card__facts">
                <dt>Assumes</dt>
                <dd>{card.assumption}</dd>
                <dt>Flags</dt>
                <dd>{card.detects}</dd>
              </dl>

              <button
                className={`btn btn--block ${selected ? "btn--ghost" : ""}`}
                onClick={() => onSelect(selected ? null : card.key)}
              >
                {selected ? "Selected" : "Select"}
              </button>
            </article>
          );
        })}
      </div>
    </div>
  );
}
