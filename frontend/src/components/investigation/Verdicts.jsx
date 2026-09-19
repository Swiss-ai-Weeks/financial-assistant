import { signed } from "../../lib/format";

function Tally({ label, count, className }) {
  if (!count) return null;

  return (
    <span className={`tally ${className}`}>
      {count} {label}
    </span>
  );
}

function label(hypothesis, index) {
  if (index > 0) return `Alternative ${index}`;

  // Ranking first does not mean the evidence backs it.
  return hypothesis.score > 0
    ? "Best supported explanation"
    : "Leading explanation · not supported by the evidence";
}

/** Competing explanations, ranked by the evidence weighed against them. */
export default function Verdicts({ hypotheses }) {
  return (
    <div className="verdicts">
      {hypotheses.map((hypothesis, index) => (
        <article
          key={hypothesis.hypothesis_id}
          className={`verdict ${index === 0 ? "is-leading" : ""}`}
        >
          <div className="verdict__head">
            <span className="eyebrow">{label(hypothesis, index)}</span>
            <span className="mono verdict__score">{signed(hypothesis.score)}</span>
          </div>

          <p className="verdict__text">{hypothesis.text}</p>

          <div className="verdict__tallies mono">
            <Tally label="support" count={hypothesis.supporting} className="up" />
            <Tally label="contradict" count={hypothesis.contradicting} className="down" />
            <Tally label="weaken" count={hypothesis.weakening} className="down" />
            <Tally label="context" count={hypothesis.context} className="muted" />
          </div>

          {hypothesis.missing_information.length > 0 && (
            <div className="verdict__gaps">
              <span className="eyebrow">Still unproven</span>
              <ul>
                {hypothesis.missing_information.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
