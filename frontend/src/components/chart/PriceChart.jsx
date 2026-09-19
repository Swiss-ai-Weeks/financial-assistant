import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
} from "lightweight-charts";

import { percent, price, signed, tone } from "../../lib/format";
import { KIND_LABEL, STRATEGY_STYLE, cssColor } from "../../lib/strategies";
import { chartOptions, toIsoDay } from "./chartTheme";

const OVERLAYS = [
  { key: "ma_fast", strategy: "trend", color: "--trend", style: LineStyle.Solid },
  { key: "ma_slow", strategy: "trend", color: "--vwap", style: LineStyle.Solid },
  { key: "vwap", strategy: "vwap", color: "--vwap", style: LineStyle.Dashed },
  { key: "twap", strategy: "twap", color: "--twap", style: LineStyle.Dashed },
];

function overlayLabel(key, series) {
  return {
    ma_fast: `MA ${series.fast} close`,
    ma_slow: `MA ${series.slow} close`,
    vwap: `VWAP ${series.vwap_window}`,
    twap: `TWAP ${series.twap_window}`,
  }[key];
}

/**
 * Candles with the strategy reference lines, anomaly
 * markers, and a clickable timeline: clicking a session
 * asks the desk for the news of that day.
 */
export default function PriceChart({
  series,
  anomalies,
  activeStrategy,
  selectedDay,
  selectedAnomalyId,
  theme,
  onSelectDay,
}) {
  const container = useRef(null);
  const handles = useRef(null);
  const onSelectDayRef = useRef(onSelectDay);

  const [hovered, setHovered] = useState(null);

  useEffect(() => {
    onSelectDayRef.current = onSelectDay;
  });

  const candlesByDay = useMemo(
    () => new Map((series?.candles ?? []).map((c) => [c.time, c])),
    [series]
  );

  // Trend lines are always drawn, like any trading desk.
  // Execution benchmarks appear with their monitor.
  const visibleOverlays = OVERLAYS.filter(
    (overlay) =>
      overlay.strategy === "trend" ||
      activeStrategy == null ||
      overlay.strategy === activeStrategy
  );

  useEffect(() => {
    const chart = createChart(container.current, {
      autoSize: true,
      ...chartOptions(),
    });

    const candles = chart.addSeries(CandlestickSeries, {
      priceLineVisible: true,
    });

    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.84, bottom: 0 },
    });

    const lines = Object.fromEntries(
      OVERLAYS.map((overlay) => [
        overlay.key,
        chart.addSeries(LineSeries, {
          lineWidth: 1.5,
          lineStyle: overlay.style,
          lastValueVisible: false,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
        }),
      ])
    );

    chart.subscribeCrosshairMove((param) => setHovered(toIsoDay(param.time)));

    chart.subscribeClick((param) => {
      const day = toIsoDay(param.time);

      if (day) onSelectDayRef.current?.(day);
    });

    handles.current = {
      chart,
      candles,
      volume,
      lines,
      markers: createSeriesMarkers(candles, []),
    };

    return () => {
      handles.current = null;
      chart.remove();
    };
  }, []);

  // Colours follow the theme.
  useEffect(() => {
    const { chart, candles, lines } = handles.current;

    chart.applyOptions(chartOptions());

    candles.applyOptions({
      upColor: cssColor("--up"),
      downColor: cssColor("--down"),
      borderUpColor: cssColor("--up"),
      borderDownColor: cssColor("--down"),
      wickUpColor: cssColor("--up"),
      wickDownColor: cssColor("--down"),
    });

    for (const overlay of OVERLAYS) {
      lines[overlay.key].applyOptions({ color: cssColor(overlay.color) });
    }
  }, [theme]);

  useEffect(() => {
    if (!series) return;

    const { chart, candles, volume, lines } = handles.current;

    candles.setData(series.candles);

    volume.setData(
      series.candles.map((candle) => ({
        time: candle.time,
        value: candle.volume,
        color:
          cssColor(candle.close >= candle.open ? "--up" : "--down") + "55",
      }))
    );

    for (const overlay of OVERLAYS) {
      lines[overlay.key].setData(
        series.candles
          .filter((candle) => candle[overlay.key] != null)
          .map((candle) => ({ time: candle.time, value: candle[overlay.key] }))
      );
    }

    chart.timeScale().fitContent();
  }, [series, theme]);

  const visibleKeys = visibleOverlays.map((overlay) => overlay.key).join();

  useEffect(() => {
    for (const overlay of OVERLAYS) {
      handles.current.lines[overlay.key].applyOptions({
        visible: visibleKeys.split(",").includes(overlay.key),
      });
    }
  }, [visibleKeys]);

  useEffect(() => {
    if (!series) return;

    const markers = anomalies
      .filter((anomaly) => candlesByDay.has(anomaly.observed_on))
      .map((anomaly) => {
        const falling = ["down", "below", "bearish", "a_below_equilibrium"]
          .includes(anomaly.direction);

        const selected = anomaly.anomaly_id === selectedAnomalyId;

        return {
          time: anomaly.observed_on,
          position: falling ? "aboveBar" : "belowBar",
          shape: falling ? "arrowDown" : "arrowUp",
          color: cssColor(STRATEGY_STYLE[anomaly.strategy].color),
          size: selected ? 2 : 1,
          // Anomalies cluster on bad days: only the selected
          // one is labelled, the rest stay colour-coded.
          text: selected ? KIND_LABEL[anomaly.kind] ?? anomaly.kind : undefined,
        };
      });

    if (selectedDay && candlesByDay.has(selectedDay)) {
      markers.push({
        time: selectedDay,
        position: "inBar",
        shape: "circle",
        color: cssColor("--accent"),
        size: 1,
      });
    }

    markers.sort((a, b) => a.time.localeCompare(b.time));
    handles.current.markers.setMarkers(markers);
  }, [series, anomalies, selectedDay, selectedAnomalyId, candlesByDay, theme]);

  const last = series?.candles.at(-1);
  const shown = candlesByDay.get(hovered) ?? last;
  const change = shown ? shown.close - shown.open : null;

  return (
    <div className="chart">
      {shown && (
        <div className="chart__legend mono">
          <div className="chart__legend-title">
            <span className="chart__symbol">{series.ticker} · 1D</span>
            <span className={tone(change)}>
              O{price(shown.open)} H{price(shown.high)} L{price(shown.low)} C
              {price(shown.close)} {signed(change)} (
              {percent((change / shown.open) * 100)})
            </span>
          </div>

          {visibleOverlays.map((overlay) => (
            <div key={overlay.key} className="chart__legend-line">
              {overlayLabel(overlay.key, series)}{" "}
              <span style={{ color: `var(${overlay.color})` }}>
                {price(shown[overlay.key])}
              </span>
            </div>
          ))}
        </div>
      )}

      <div ref={container} className="chart__canvas" />
    </div>
  );
}
