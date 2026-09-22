# Financial anomaly report

**Tesla (TSLA) 3-Year Market Anomaly Analysis**
*Period: 2023-09-22 to 2026-09-21*

### 1. Key Findings

- **Total anomalies detected:** 41
- **Positive anomalies:** 24
- **Negative anomalies:** 17

**Methodology:** Anomalies were identified using a rolling window of 20 trading days. A day was flagged if the absolute volume z-score exceeded 2 and the absolute daily return percentage exceeded 2. The first 20 trading days of the period were excluded from the analysis due to insufficient rolling statistics.

### 2. Most Extreme Events

The following events represent the most significant deviations from normal trading patterns based on the combined criteria of high volume and substantial price movement:

| Date | Return % | Volume Z-Score | Close Price | Classification |
| :--- | :--- | :--- | :--- | :--- |
| 2025-06-05 | -14.26 | 9.36 | 284.70 | Negative |
| 2026-07-23 | -14.52 | 6.32 | 319.69 | Negative |
| 2025-09-12 | 7.36 | 6.03 | 395.94 | Positive |
| 2024-01-25 | -12.13 | 8.17 | 182.63 | Negative |
| 2024-10-24 | 21.92 | 5.81 | 260.48 | Positive |

**Event Analysis:**
*   **2025-06-05:** This event recorded the highest volume z-score (9.36) in the dataset, accompanied by a significant negative return of -14.26%.
*   **2026-07-23:** A substantial negative return of -14.52% was observed with a volume z-score of 6.32.
*   **2025-09-12:** A notable positive return of 7.36% occurred alongside elevated volume (z-score of 6.03).
*   **2024-01-25:** Characterized by a sharp decline of -12.13% with high trading volume (z-score of 8.17).
*   **2024-10-24:** This event stands out for a very strong positive return of 21.92% with a volume z-score of 5.81.

### 3. Key Observations

* **Pattern Distribution:** Of the 41 total anomalies detected, 24 were classified as positive anomalies (positive returns with high volume) and 17 as negative anomalies (negative returns with high volume).
* **Statistical Co-occurrence:** The data indicates that days with high trading volume and significant daily returns occurred throughout the three-year period. It is important to note that daily price and volume data alone cannot establish causation. Negative returns observed with high volume indicate co-occurrence. Similarly, positive returns with high volume do not inherently indicate buying pressure.
* **Volume Extremes:** The analysis identified several instances where volume z-scores were notably high (exceeding 5.0). These events are primarily concentrated in late 2024 and mid-2025. However, without additional context such as fundamental news or longer-term trend analysis, the specific drivers of these volume spikes remain unknown based solely on the daily price and volume data provided.
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
