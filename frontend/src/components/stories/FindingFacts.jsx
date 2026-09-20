import { money, tone } from "../../lib/format";

/**
 * The post-mortem of one anomaly: what it cost, whether a
 * hedge would have helped, the signal that was visible at
 * the time, and why the two securities are treated as related.
 */
export default function FindingFacts({ finding }) {
  if (!finding) return null;

  const { relationship: link } = finding;

  return (
    <section className="facts">
      <div className="facts__row">
        <div>
          <span className="eyebrow">Portfolio impact</span>
          <strong className={`mono ${tone(finding.impact)}`}>
            {finding.impact < 0 ? "−" : "+"}${money(Math.abs(finding.impact))}
          </strong>
        </div>

        {finding.hedged_impact != null && (
          <div>
            <span className="eyebrow">Had it been hedged</span>
            <strong className={`mono ${tone(finding.hedged_impact)}`}>
              {finding.hedged_impact < 0 ? "−" : "+"}$
              {money(Math.abs(finding.hedged_impact))}
            </strong>
          </div>
        )}
      </div>

      <div className="facts__block">
        <span className="eyebrow">The signal you could have seen</span>
        <p>{finding.missed_signal}</p>
      </div>

      {link && (
        <div className="facts__block">
          <span className="eyebrow">Why are these two related?</span>
          <p>
            Over the {link.formation_start} → {link.formation_end} formation window,
            before this period began, their returns were correlated{" "}
            <span className="mono">{link.correlation.toFixed(2)}</span> and their
            prices were cointegrated (p ={" "}
            <span className="mono">{link.pvalue.toFixed(4)}</span>): log{" "}
            {link.ticker_a} tracked{" "}
            <span className="mono">{link.beta.toFixed(2)}</span> × log {link.ticker_b},
            and gaps closed with a half-life of{" "}
            <span className="mono">
              {link.half_life_days ? `${link.half_life_days.toFixed(1)} sessions` : "—"}
            </span>
            . The economic chain behind that is in the ClaimGraph.
          </p>
        </div>
      )}
    </section>
  );
}
