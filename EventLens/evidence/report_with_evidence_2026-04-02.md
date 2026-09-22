# Financial anomaly report

**TSLA 3-Year Market Anomaly Analysis (2023-09-22 to 2026-09-22)**

**1. Key Findings**

- Total anomalies detected: 41
- Positive anomalies: 24
- Negative anomalies: 17

The detection methodology employed a rolling window of 20 trading days with two simultaneous thresholds: an absolute volume z-score exceeding 2 and an absolute daily return percentage exceeding 2%. This filter identified days where both trading volume and price movement were statistically unusual. The first 20 trading days of the period were excluded from the analysis due to insufficient rolling history for volume z-score calculation.

**2. Most Extreme Events**

The following five events represent the most significant anomalies by volume z-score:

- **2025-06-05**: Volume z-score of 9.36 with a return of -14.26%. This event recorded the highest volume anomaly in the three-year period, accompanied by a substantial negative return.
- **2026-07-23**: Volume z-score of 6.32 with a return of -14.52%. This event demonstrated extreme volume activity alongside a significant price decline.
- **2024-01-25**: Volume z-score of 8.17 with a return of -12.13%. An early-period extreme volume event with negative returns.
- **2025-09-12**: Volume z-score of 6.03 with a return of 7.36%. Notable for high volume coinciding with positive price movement.
- **2024-10-24**: Volume z-score of 5.81 with a return of 21.92%. This event featured the highest positive return among the top volume anomalies.

These events were identified because they satisfied the detection criteria of simultaneously exceeding the volume z-score threshold of 2 and the return threshold of 2% in absolute terms.

**3. Key Observations**

- The analysis identified 24 positive anomalies (days where the absolute return exceeded 2% regardless of direction) and 17 negative anomalies, totaling 41 anomaly days.
- The detection rule requires both unusual volume and unusual price movement on the same day; therefore, these events represent co-occurrence rather than established causation.
- Daily price and volume data alone cannot establish which metric preceded the other or whether one caused the observed movement.
- No temporal clustering statistics are provided in the source data.
- The dataset covers 732 valid analysis days out of 752 total trading days, indicating that the majority of days exhibited normal volume and return patterns within the defined thresholds.
---
**Report Summary**
The analysis identified 41 anomalies: 17 with negative returns and 24 with positive returns. Each event satisfies the specified volume and absolute-return thresholds.

---

# Evidence appendix (descriptive; not causal)

# Daily evidence map: TSLA 2026-04-02
As-of: 2026-04-02T20:00:00+00:00 · selected groups: 12 · model calls: 0
Historical retrieval ranks from original news/ranker.py; no new scores or causal claims.

| Position | Article/event title proxy | Prior-day | Same-day, onset unknown | Quotes matched | Review |
|---:|---|---:|---:|---:|---|
| 1 | Tesla's First-Quarter Deliveries Miss Views as Wedbush Flags Tough Demand Backdrop | 0 | 1 | 0 | not assessed |
| 2 | Tesla's China-Made EV Sales Leap Nearly 9% In March | 0 | 1 | 0 | not assessed |
| 3 | Why Tesla (TSLA) Stock Is Up Today | 1 | 0 | 0 | not assessed |
| 4 | Gary Black Says TSLA Has Underperformed Nasdaq For 5 Years Because It Has Never Lived Up To Unsupervised FSD Hype: 'TSLA Still Has Only 9 Robotaxis' | 2 | 0 | 0 | not assessed |
| 5 | Assessing Tesla (TSLA) Valuation As Shares Weaken And AI Narratives Diverge | 1 | 0 | 0 | not assessed |
| 6 | Tesla (TSLA) Rises Higher Than Market: Key Facts | 1 | 0 | 0 | not assessed |
| 7 | GLJ Maintains Sell Rating on Tesla (TSLA) | 2 | 0 | 0 | not assessed |
| 8 | The Tesla Robotaxi Story Is A Myth: Why I'm Maintaining My Strong Sell Into Q1 Earnings | 1 | 0 | 0 | not assessed |
| 9 | Blue Owl limits fund withdrawals, mortgage rates rise for fifth week | 0 | 1 | 0 | not assessed |
| 10 | Tesla's Q1 Delivery Numbers 'Underwhelming,' But Not Surprising Given Current Global EV Backdrop, Wedbush Says | 0 | 1 | 0 | not assessed |
| 11 | Tesla Stock Hasn’t Looked This Cheap in a While | 0 | 1 | 0 | not assessed |
| 12 | Tesla Slides 3% on Delivery Shortfall: Why the $20 Billion Robotaxi Bet Makes This Miss Hard to Judge | 0 | 1 | 0 | not assessed |

No model judgement or quote proves a stock-price cause. Market anomaly detector and original ranker remain unchanged.
