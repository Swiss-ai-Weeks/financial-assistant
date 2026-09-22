# Financial anomaly report

**Amazon (AMZN) Financial Anomaly Analysis: 2-Year Period**
*September 23, 2024, to September 22, 2026*

### 1. Key Findings

- **Total anomalies detected:** 27
- **Positive anomalies:** 13
- **Negative anomalies:** 14

**Methodology:** Anomalies were identified using a rolling 20-day window. An event was flagged when the absolute volume z-score exceeded 2.0 **and** the absolute daily return percentage exceeded 2.0. The first 20 trading days of the period were excluded from valid analysis due to the initialization of rolling statistics.

### 2. Most Extreme Events

The following events represent the most significant deviations from normal trading patterns based on the detection criteria:

| Date | Close Price | Volume Z-Score | Return % | Classification |
| :--- | :--- | :--- | :--- | :--- |
| 2026-06-26 | 232.69 | 14.53 | +2.50 | Positive anomaly |
| 2026-07-31 | 271.58 | 5.62 | +15.32 | Positive anomaly |
| 2026-02-05 | 222.69 | 9.87 | -4.42 | Negative anomaly |
| 2026-02-06 | 210.32 | 8.84 | -5.55 | Negative anomaly |
| 2026-07-30 | 235.50 | 8.59 | +3.90 | Positive anomaly |

**Event Analysis:**
- **2026-06-26:** This event recorded the highest volume z-score (14.53) within the dataset. The stock closed at $232.69 with a positive return of +2.50%, meeting both the volume and return thresholds for anomaly detection.
- **2026-07-31:** This event represents the largest positive return (15.32%) identified in the analysis period. Despite a relatively moderate volume z-score of 5.62, the magnitude of the price movement qualified it as a positive anomaly.
- **2026-02-05 & 2026-02-06:** These consecutive trading days featured significant negative returns (-4.42% and -5.55%) accompanied by high volume z-scores (9.87 and 8.84). Both events meet the detection criteria for negative anomalies.
- **2026-07-30:** This event recorded a positive return of +3.90% with a high volume z-score of 8.59, qualifying it as a positive anomaly.

### 3. Key Observations

- **Statistical Distribution:** Of the 27 total anomalies detected, 13 were classified as positive and 14 as negative, indicating a nearly balanced distribution of extreme price movements relative to volume over the two-year period.
- **Volume and Return Co-occurrence:** The detection framework identifies days where high volume and significant price moves occur simultaneously. It is important to note that daily price and volume data alone cannot establish causation; the data reflects co-occurrence rather than directional pressure.
- **Extreme Volume Events:** The event on 2026-06-26 stands out with a volume z-score of 14.53, which is substantially higher than the threshold of 2.0 used for detection. The top volume anomalies in the dataset generally feature z-scores exceeding 8.0, while the top return anomalies feature returns exceeding 8.0% in magnitude.
- **Observations of Co-occurring Events:** The analysis period includes observations of multiple anomalies within short timeframes (such as the consecutive negative events in February 2026). These observations reflect statistical co-occurrence of events based on the provided data.
---
**Report Summary**
The analysis identified 27 anomalies: 14 with negative returns and 13 with positive returns. Each event satisfies the specified volume and absolute-return thresholds.

---

# Evidence appendix (descriptive; not causal)

# Daily evidence map: AMZN 2026-06-25
As-of: 2026-06-25T20:00:00+00:00 · selected groups: 12 · model calls: 0
Historical retrieval ranks from original news/ranker.py; no new scores or causal claims.

| Position | Article/event title proxy | Prior-day | Same-day, onset unknown | Quotes matched | Review |
|---:|---|---:|---:|---:|---|
| 1 | Amazon (AMZN) BofA Sees Q2 Revenue Beat Despite Prime Day Timing Shift | 1 | 0 | 0 | not assessed |
| 2 | S&P 500, Nasdaq And Dow End Holiday-Shortened Week Higher As Investors Cheer US-Iran Peace Deal — SPCX, AMZN, ONDS, NFLX, TTWO In Focus | 1 | 0 | 0 | not assessed |
| 3 | Should Amazon’s US$10 Billion Missouri AI Bet and Trainium Chip Sales Shift AMZN’s Cloud Narrative? | 1 | 0 | 0 | not assessed |
| 4 | Amazon.com (AMZN) Gains 3% After Announcing $10 Billion Missouri Data Center Investment | 1 | 0 | 0 | not assessed |
| 5 | BMO Capital Reiterates Buy Rating on Amazon.com (AMZN) Stock | 0 | 1 | 0 | not assessed |
| 6 | Why Amazon Is Sliding Right Before Its Biggest Sales Week Of The Year | 1 | 0 | 0 | not assessed |
| 7 | Amazon Prime Day Set to Generate Record Online Spending as Retailers Compete for Shoppers (AMZN) | 2 | 0 | 0 | not assessed |
| 8 | Amazon (AMZN) Stock Gets Fair Value Bump As Analysts Weigh AWS And AI Spending | 1 | 0 | 0 | not assessed |
| 9 | Amazon Pledges $48B to Scale AI Infrastructure in India: What's Ahead? | 0 | 1 | 0 | not assessed |
| 10 | What's Going On With Amazon Stock Thursday? | 0 | 1 | 0 | not assessed |
| 11 | Wall Street Is Fixated on the Wrong Numbers: Why This Trillion-Dollar Cash Machine Is a No-Brainer Buy Right Now | 1 | 0 | 0 | not assessed |
| 12 | Is Amazon.com, Inc. (AMZN) the Best AI Chip Stock to Buy for the Long Term? | 1 | 1 | 0 | not assessed |

No model judgement or quote proves a stock-price cause. Market anomaly detector and original ranker remain unchanged.
