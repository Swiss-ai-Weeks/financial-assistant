# Financial anomaly report

**NVDA 3-Year Anomaly Analysis (2023-09-22 to 2026-09-21)**

**Key Findings**
- Total anomalies detected: 31
- Positive anomalies: 13
- Negative anomalies: 18

The detection methodology identified anomalies as days where the absolute volume z-score exceeded 2.0 and the absolute daily return percentage exceeded 2.0, calculated using a rolling 20-trading-day window. The first 20 trading days of the period were excluded from the analysis due to insufficient rolling window data.

**Most Extreme Events**
The following five events represent the most significant anomalies by volume z-score:

1. **2025-01-27**: Volume z-score of 11.62 with a return of -16.97%. This event stands out as the most extreme anomaly in the dataset, with volume significantly above normal levels accompanied by a substantial negative return.

2. **2026-08-27**: Volume z-score of 7.35 with a return of +8.74%. This represents the second-most extreme volume anomaly and the only positive return among the top volume events.

3. **2023-11-22**: Volume z-score of 6.78 with a return of -2.46%. An early-period anomaly with moderate volume elevation and slight negative return.

4. **2026-02-26**: Volume z-score of 5.89 with a return of -5.46%. A later-period anomaly with notable volume elevation and moderate negative return.

5. **2024-04-19**: Volume z-score of 5.75 with a return of -10.0%. A significant anomaly from the middle of the period with high volume and substantial negative return.

**Key Observations**
- The analysis identified 31 total anomalies across 731 valid trading days, representing approximately 4.2% of the total period.
- Negative anomalies outnumbered positive anomalies (18 vs 13), indicating a slight predominance of downside events meeting the detection criteria.
- Volume spikes and price movements co-occurred on all detected anomaly days, but daily price and volume data alone cannot establish causation or determine which variable preceded the other.
- The detection threshold required both elevated volume (z-score > 2) and significant price movement (return > 2% in absolute value), ensuring that only days with substantial activity in both metrics were flagged.
- The rolling 20-day window methodology means that early-period anomalies may reflect changing market conditions as the analysis window stabilized.

*Report generated from Python analysis of NVDA 3-year data using specified anomaly detection rules.*

---

# Evidence appendix (descriptive; not causal)

# Daily evidence map: NVDA 2026-08-27
As-of: 2026-08-27T20:00:00+00:00 · selected groups: 0 · model calls: 0
Historical retrieval ranks from original news/ranker.py; no new scores or causal claims.

| Position | Article/event title proxy | Prior-day | Same-day, onset unknown | Quotes matched | Review |
|---:|---|---:|---:|---:|---|

No model judgement or quote proves a stock-price cause. Market anomaly detector and original ranker remain unchanged.
