import { useEffect, useRef } from "react";
import { LineSeries, LineStyle, createChart } from "lightweight-charts";

import { cssColor } from "../../lib/strategies";
import { chartOptions } from "./chartTheme";

/**
 * z-score of a cointegration spread against its frozen
 * formation-window fit, with the entry bands a pairs
 * trader would act on.
 */
export default function SpreadChart({ spread, theme }) {
  const container = useRef(null);

  useEffect(() => {
    if (!spread) return undefined;

    const chart = createChart(container.current, {
      autoSize: true,
      ...chartOptions(),
    });

    const line = chart.addSeries(LineSeries, {
      color: cssColor("--pairs"),
      lineWidth: 2,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });

    line.setData(
      spread.points.map((point) => ({ time: point.time, value: point.z_score }))
    );

    for (const level of [spread.entry, -spread.entry]) {
      line.createPriceLine({
        price: level,
        color: cssColor("--down"),
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
        title: `${level > 0 ? "+" : "−"}${spread.entry}σ entry`,
      });
    }

    line.createPriceLine({
      price: 0,
      color: cssColor("--text-faint"),
      lineStyle: LineStyle.Dotted,
      lineWidth: 1,
      axisLabelVisible: false,
      title: "equilibrium",
    });

    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [spread, theme]);

  if (!spread) {
    return null;
  }

  return (
    <div className="chart">
      <div className="chart__legend mono">
        <div className="chart__legend-title">
          <span className="chart__symbol">
            {spread.ticker_a} / {spread.ticker_b} · spread z-score
          </span>
        </div>
        <div className="chart__legend-line">
          log({spread.ticker_a}) − {spread.beta.toFixed(3)} × log(
          {spread.ticker_b}) · fit frozen on {spread.formation_end}
        </div>
      </div>

      <div ref={container} className="chart__canvas" />
    </div>
  );
}
