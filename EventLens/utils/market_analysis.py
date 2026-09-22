import yfinance as yf
import pandas as pd


def get_market_data(
    ticker: str,
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    if start_date:
        df = yf.download(
            ticker,
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False,
        )
    else:
        df = yf.download(
            ticker,
            period=period or "1y",
            auto_adjust=True,
            progress=False,
        )

    if df.empty:
        raise ValueError(f"No market data found for {ticker}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df.dropna(subset=["Volume"])


def calculate_anomalies(
    df,
    window=20,
    z_threshold=2,
    return_threshold=0.02,
):
    df = df.copy()

    df["volume_mean_20d"] = (
        df["Volume"].shift(1).rolling(window).mean()
    )

    df["volume_std_20d"] = (
        df["Volume"].shift(1).rolling(window).std()
    )

    df["volume_zscore"] = (
        (df["Volume"] - df["volume_mean_20d"])
        / df["volume_std_20d"]
    )

    df["return"] = df["Close"].pct_change()

    df["interesting_anomaly"] = (
        (df["volume_zscore"].abs() > z_threshold)
        & (df["return"].abs() > return_threshold)
    )

    return df


def get_anomalies(df):
    return df[df["interesting_anomaly"]]