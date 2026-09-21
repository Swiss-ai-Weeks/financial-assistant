import { percent, tone } from "../../lib/format";
import { metricValue } from "../../lib/portfolio";

/**
 * One calculated ratio, as a percentage.
 *
 * A metric the server could not calculate is never a zero:
 * a tile spells the reason out, a table cell shows a dash
 * and keeps the reason on hover, where a sentence would
 * break the column.
 */
export default function MetricValue({ metric, toned = true, plain = false, compact = false }) {
  const { value, reason } = metricValue(metric);

  if (value == null) {
    return (
      <span className="portfolio-na" title={reason}>
        {compact ? "—" : reason}
      </span>
    );
  }

  const scaled = value * 100;

  return (
    <span className={`mono ${toned ? tone(scaled) : ""}`} title={metric.formula}>
      {plain ? `${scaled.toFixed(2)}%` : percent(scaled)}
    </span>
  );
}
