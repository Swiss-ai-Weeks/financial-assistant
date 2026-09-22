from langchain_core.tools import tool
from utils.market_analysis import (
    get_market_data,
    calculate_anomalies,
    get_anomalies,
)

@tool
def analyze_ticker(
    ticker: str,
    period: str = "1y",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Analyze unusual price and volume activity.

    Use period for relative ranges (1y, 2y, 5y).
    Use start_date and end_date for explicit ranges.
    """

    df = get_market_data(
        ticker=ticker,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )

    df = calculate_anomalies(df)
    anomalies = get_anomalies(df)

    events = []

    for date, row in anomalies.iterrows():
        events.append({
            "date": str(date.date()),
            "close": round(float(row["Close"]), 2),
            "volume_zscore": round(
                float(row["volume_zscore"]), 2
            ),
            "return_pct": round(
                float(row["return"]) * 100, 2
            ),
        })

    # Calculate statistics using Python, not the LLM

    positive = anomalies[anomalies["return"] > 0]
    negative = anomalies[anomalies["return"] < 0]

    top_volume = sorted(
        events,
        key=lambda x: abs(x["volume_zscore"]),
        reverse=True,
    )[:5]

    top_returns = sorted(
        events,
        key=lambda x: abs(x["return_pct"]),
        reverse=True,
    )[:5]

    summary = {
        "total_trading_days": len(df),
        "valid_analysis_days": int(
            df["volume_zscore"].notna().sum()
        ),
        "total_anomalies": len(events),
        "positive_anomalies": len(positive),
        "negative_anomalies": len(negative),
        "top_volume_anomalies": top_volume,
        "top_return_anomalies": top_returns,
    }

    return {
        "ticker": ticker,
        "period": period if not start_date else None,
        "start_date": str(df.index.min().date()),
        "end_date": str(df.index.max().date()),
        "methodology": {
            "rolling_window": 20,
            "volume_zscore_threshold": 2,
            "absolute_return_threshold_pct": 2,
            "condition": (
                "abs(volume_zscore) > 2 AND "
                "abs(daily_return_pct) > 2"
            ),
            "note": (
                "Rolling statistics use the previous "
                "20 trading days. The first 20 rows "
                "do not have a valid volume z-score."
            ),
        },
        "summary": summary,
        "anomaly_count": len(events),
        "events": events,
    }


