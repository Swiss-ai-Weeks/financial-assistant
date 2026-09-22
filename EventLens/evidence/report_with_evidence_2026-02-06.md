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

# Daily evidence map: NVDA 2026-02-06
As-of: 2026-02-06T21:00:00+00:00 · selected groups: 12 · model calls: 0
Historical retrieval ranks from original news/ranker.py; no new scores or causal claims.

| Position | Article/event title proxy | Prior-day | Same-day, onset unknown | Quotes matched | Review |
|---:|---|---:|---:|---:|---|
| 1 | Did NVIDIA's (NVDA) Paused OpenAI Megadeal Just Reframe Its AI Infrastructure Investment Narrative? | 4 | 0 | 0 | not assessed |
| 2 | Claude 5 Will Probably Launch In Q1: Here's What GOOGL, NVDA, AMZN Investors Should Know | 1 | 0 | 0 | not assessed |
| 3 | Jim Cramer Shares Key Insights About NVIDIA Corporation (NVDA)’s China Sales | 1 | 0 | 0 | not assessed |
| 4 | Nvidia CEO Huang says AI buildout to take 7-8 years, demand "sky high" | 0 | 1 | 0 | not assessed |
| 5 | Nvidia Reportedly Nears Record $20 Billion OpenAI Investment As Jensen Huang And Sam Altman Deny Reports Of Strained Partnership | 1 | 0 | 0 | not assessed |
| 6 | Is It Worth Investing in Nvidia (NVDA) Based on Wall Street's Bullish Views? | 0 | 1 | 0 | not assessed |
| 7 | Trump Approved Nvidia's H200 China Chip Sales — But State Department Review Is Holding Things Up: Report | 1 | 0 | 0 | not assessed |
| 8 | Nvidia Partner Hon Hai’s Sales Soar in Sign of Strong AI Demand | 1 | 0 | 0 | not assessed |
| 9 | NVIDIA Corporation (NVDA): A Bull Case Theory | 1 | 0 | 0 | not assessed |
| 10 | Why this analyst likes AMD over Nvidia: The rate of change is faster | 0 | 1 | 0 | not assessed |
| 11 | Equity Markets Rise Intraday as Nvidia Drives Tech Rally; Amazon Slumps | 0 | 1 | 0 | not assessed |
| 12 | NVIDIA vs. Palantir: One AI Stock is a Clear Buy Right Now | 1 | 0 | 0 | not assessed |

No model judgement or quote proves a stock-price cause. Market anomaly detector and original ranker remain unchanged.
