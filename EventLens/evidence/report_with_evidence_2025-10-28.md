# Financial anomaly report

**NVDA 2-Year Market Anomaly Analysis (2024-09-23 to 2026-09-22)**

**1. Key Findings**

- Total anomalies detected: 19
- Positive anomalies: 9
- Negative anomalies: 10

The detection methodology identified anomalies as days where the absolute volume z-score exceeded 2.0 and the absolute daily return percentage exceeded 2.0, calculated using a rolling 20-trading-day window. The analysis period consisted of 501 total trading days, with valid volume z-scores available for 481 of those days.

**2. Most Extreme Events**

The following five events represent the most significant anomalies based on volume and return metrics:

- **2025-01-27**: Volume z-score of 11.62 with a return of -16.97%. This event is the most extreme anomaly in the dataset, characterized by exceptionally high trading volume coinciding with a substantial price decline.

- **2026-08-27**: Volume z-score of 7.35 with a return of 8.74%. This represents a significant positive anomaly where high volume coincided with strong price appreciation.

- **2025-02-26**: Volume z-score of 5.89 with a return of -5.46%. This event shows elevated volume associated with a moderate price decline.

- **2025-04-04**: Volume z-score of 4.89 with a return of -7.36%. This anomaly features above-average volume with a notable negative return.

- **2025-04-07**: Volume z-score of 4.25 with a return of 3.53%. This event demonstrates high volume coinciding with a positive price movement.

**3. Key Observations**

The dataset contains 19 total anomalies, with a slight predominance of negative events (10) over positive events (9). The detection threshold requires both elevated volume and significant price movement, ensuring that only days with substantial market activity meeting both criteria are captured.

It is important to note that the analysis uses daily price and volume data. Negative returns with high volume indicate co-occurrence, not causation. Similarly, positive returns with high volume demonstrate co-occurrence without implying buying pressure. The data does not support claims about market sentiment, price precedents, or temporal clustering beyond what is statistically evident in the anomaly counts provided.

The first 20 trading days of the analysis period do not have valid volume z-scores due to the rolling window methodology, which may affect the completeness of the early-period analysis.
---
**Report Summary**
The analysis identified 19 anomalies: 10 with negative returns and 9 with positive returns. Each event satisfies the specified volume and absolute-return thresholds.

---

# Evidence appendix (descriptive; not causal)

# Daily evidence map: NVDA 2025-10-28
As-of: 2025-10-28T20:00:00+00:00 · selected groups: 12 · model calls: 0
Historical retrieval ranks from original news/ranker.py; no new scores or causal claims.

| Position | Article/event title proxy | Prior-day | Same-day, onset unknown | Quotes matched | Review |
|---:|---|---:|---:|---:|---|
| 1 | Blockbuster $40b AI Investment Is Only 10% of What’s Coming (NVDA, MSFT, META, BLK) | 1 | 0 | 0 | not assessed |
| 2 | Nvidia Supplier Foxconn Goes All-In On AI With $1.37 Billion Supercomputing Investment | 0 | 1 | 0 | not assessed |
| 3 | Analyst on NVIDIA (NVDA) AI Deals and Debt Concerns: ‘We Are Not Running Out of Organic Capital’ | 0 | 1 | 0 | not assessed |
| 4 | Nvidia: The Big 3 Issues Before Earnings | 1 | 0 | 0 | not assessed |
| 5 | Bubble Watch: AI Is Changing Everything, But No One Pays For It (MSFT, NVDA) | 1 | 0 | 0 | not assessed |
| 6 | Betting Big on Intel: Is INTC Stock a Buy Before Oct. 23 Earnings? | 1 | 0 | 0 | not assessed |
| 7 | Does NVIDIA's (NVDA) Desktop AI Supercomputer Shift the Long-Term Growth Outlook? | 1 | 0 | 0 | not assessed |
| 8 | Nvidia: 2 'What Ifs' That Could Change Everything | 0 | 1 | 0 | not assessed |
| 9 | What is the Next NVIDIA (NVDA)? Brad Gerstner Answers | 0 | 1 | 0 | not assessed |
| 10 | Former Biden Adviser Explains What Concerns Him About NVIDIA (NVDA)-Led AI ‘Bubble’ | 1 | 0 | 0 | not assessed |
| 11 | Nvidia (NVDA): Exploring Valuation After Recent Steady Share Price Gains | 0 | 1 | 0 | not assessed |
| 12 | Beyond Meat, Tesla, and the aspiring Nvidia rival: Trending Stocks | 1 | 0 | 0 | not assessed |

No model judgement or quote proves a stock-price cause. Market anomaly detector and original ranker remain unchanged.
