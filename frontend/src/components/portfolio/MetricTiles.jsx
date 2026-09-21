import { largestHolding } from "../../lib/portfolio";
import MetricValue from "./MetricValue";

function Tile({ label, caption, children }) {
  return (
    <div className="portfolio-tile">
      <span className="eyebrow">{label}</span>
      <span className="portfolio-tile__value">{children}</span>
      {caption && <span className="portfolio-tile__caption muted">{caption}</span>}
    </div>
  );
}

/**
 * The book in six figures. Every one is a server-side
 * calculation on cached closes; the page only formats, so
 * a tile and the provenance under it always agree.
 */
export default function MetricTiles({ analysis }) {
  const { summary, concentration, weights } = analysis;

  const sample = summary
    ? `${summary.sessions} sessions · ${summary.start} → ${summary.end}`
    : null;

  const largest = largestHolding(weights);
  const hhi = concentration?.hhi;

  return (
    <div className="portfolio-tiles">
      <Tile label="20-session return" caption="Compounded, fixed daily weights">
        <MetricValue metric={analysis.return_20} />
      </Tile>

      <Tile label="63-session return" caption="Compounded, fixed daily weights">
        <MetricValue metric={analysis.return_63} />
      </Tile>

      <Tile label="Realised volatility · annualised" caption={sample}>
        <MetricValue metric={summary?.volatility} toned={false} plain />
      </Tile>

      <Tile label="Max drawdown" caption={sample}>
        <MetricValue metric={summary?.max_drawdown} />
      </Tile>

      <Tile label="Largest weight" caption={largest}>
        {Number.isFinite(concentration?.largest_weight) ? (
          <span className="mono">{(concentration.largest_weight * 100).toFixed(1)}%</span>
        ) : (
          <span className="portfolio-na">Not calculated</span>
        )}
      </Tile>

      <Tile
        label="HHI concentration"
        // 1 / HHI: how many equal positions would be as concentrated.
        caption={hhi > 0 ? `≈ ${(1 / hhi).toFixed(1)} equal positions` : null}
      >
        {Number.isFinite(hhi) ? (
          <span className="mono">{hhi.toFixed(3)}</span>
        ) : (
          <span className="portfolio-na">Not calculated</span>
        )}
      </Tile>
    </div>
  );
}
