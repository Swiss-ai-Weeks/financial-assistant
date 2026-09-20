import { percent } from "../../lib/format";
import HorizonSlider from "./HorizonSlider";

/**
 * Header of the "Now" mode. It is about ONE security, so it
 * says nothing about the book: the question, the verdict at
 * the chosen timescale, and the timescale control itself.
 */
export default function CopilotStrip({ ticker, microscope, horizon, onHorizon }) {
  const reading = microscope?.reading;

  return (
    <section className="strip strip--copilot">
      <div className="strip__headline">
        <span className="eyebrow">Copilot · as of {microscope?.as_of ?? "…"}</span>
        <strong>
          What is unusual about <span className="mono">{ticker}</span> right now?
        </strong>
      </div>

      <div className="strip__figure">
        <span className="eyebrow">At {horizon.toUpperCase()}</span>
        <span className={`mono ${reading?.unusual ? "down" : ""}`}>
          {reading
            ? `${Math.abs(reading.z_score).toFixed(1)}σ · ${
                reading.unusual ? "unusual" : "ordinary"
              }`
            : "…"}
        </span>
      </div>

      <div className="strip__figure">
        <span className="eyebrow">Abnormal return</span>
        <span className="mono">{percent(reading?.abnormal_return_pct, 1)}</span>
      </div>

      <div className="strip__figure strip__figure--wide">
        <span className="eyebrow">Move the timescale: the verdict changes</span>
        <HorizonSlider
          ticks={microscope?.ticks ?? []}
          horizon={horizon}
          onChange={onHorizon}
        />
      </div>
    </section>
  );
}
