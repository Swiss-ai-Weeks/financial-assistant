from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict


# Sessions per horizon. An hourly horizon needs an
# intraday feed and is deliberately absent.
HORIZONS: dict[str, int] = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "1y": 252,
}

ESTIMATION_SESSIONS = 252
UNUSUAL_Z = 2.0
FOLLOWED_Z = 1.0


class HorizonReading(BaseModel):
    """
    How unusual one security is over one horizon.

    "Unusual" has no single definition: a move that is
    extreme for a day can be ordinary for a quarter, so
    every figure is relative to the security's own history
    AT THAT HORIZON.
    """

    model_config = ConfigDict(frozen=True)

    horizon: str
    sessions: int

    return_pct: float
    benchmark_return_pct: float
    beta: float

    # Return not explained by the market model.
    abnormal_return_pct: float
    z_score: float
    unusual: bool

    volume_multiple: float
    volume_unusual: bool


class PeerReading(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    correlation: float
    abnormal_return_pct: float
    z_score: float

    # Whether the peer moved with the subject.
    followed: bool


def wide(prices: pd.DataFrame, column: str = "close") -> pd.DataFrame:
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()

    return frame.pivot_table(
        index="date", columns="ticker", values=column, aggfunc="last"
    ).sort_index()


def abnormal_return_series(
    closes: pd.Series,
    benchmark: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """
    Daily abnormal log returns under a market model, and
    the beta used for each day.

    Beta for day t is estimated on the ESTIMATION_SESSIONS
    ending at t-1, so the move being judged never takes
    part in its own benchmark.
    """

    returns = np.log(closes).diff()
    market = np.log(benchmark.reindex(closes.index)).diff()

    covariance = returns.rolling(ESTIMATION_SESSIONS).cov(market)
    variance = market.rolling(ESTIMATION_SESSIONS).var()

    beta = (covariance / variance).shift(1)

    return returns - beta * market, beta


def horizon_zscores(abnormal: pd.Series, sessions: int) -> tuple[pd.Series, pd.Series]:
    """
    Cumulative abnormal return over the horizon, and how
    many standard deviations it represents.

    The yardstick is the event-study one: daily abnormal
    volatility, measured on the year BEFORE the horizon
    began, scaled by the square root of the horizon.

    Standardising against past same-horizon moves instead
    looks more direct but breaks at long horizons: a few
    years of data hold only a few independent one-year
    windows, their spread is badly underestimated, and an
    ordinary year reads as a five-sigma event.
    """

    cumulative = abnormal.rolling(sessions).sum()

    daily = abnormal.shift(sessions).rolling(ESTIMATION_SESSIONS).std()
    scale = daily * np.sqrt(sessions)

    return cumulative, cumulative / scale.replace(0.0, np.nan)


def read_horizon(
    prices: pd.DataFrame,
    *,
    ticker: str,
    benchmark: str,
    horizon: str,
) -> HorizonReading:
    sessions = HORIZONS[horizon]

    closes = wide(prices)
    volumes = wide(prices, "volume")[ticker].dropna()

    asset = closes[ticker].dropna()
    market = closes[benchmark]

    abnormal, beta = abnormal_return_series(asset, market)
    cumulative, z = horizon_zscores(abnormal, sessions)

    if pd.isna(z.iloc[-1]):
        raise ValueError(
            f"Not enough history to judge {ticker} over {horizon}."
        )

    # Volume of the horizon against the period just before
    # it, which must be long enough to be a baseline.
    baseline = max(sessions * 3, 60)
    recent = volumes.iloc[-sessions:].mean()
    before = volumes.iloc[-(sessions + baseline):-sessions].mean()
    volume_multiple = float(recent / before) if before else 1.0

    market_on_asset_days = market.reindex(asset.index)

    return HorizonReading(
        horizon=horizon,
        sessions=sessions,
        return_pct=float(asset.iloc[-1] / asset.iloc[-sessions - 1] - 1) * 100,
        benchmark_return_pct=float(
            market_on_asset_days.iloc[-1]
            / market_on_asset_days.iloc[-sessions - 1]
            - 1
        ) * 100,
        beta=float(beta.iloc[-1]),
        abnormal_return_pct=float(np.expm1(cumulative.iloc[-1])) * 100,
        z_score=float(z.iloc[-1]),
        unusual=abs(float(z.iloc[-1])) >= UNUSUAL_Z,
        volume_multiple=volume_multiple,
        volume_unusual=volume_multiple >= 1.5,
    )


def read_peers(
    prices: pd.DataFrame,
    *,
    ticker: str,
    benchmark: str,
    horizon: str,
    limit: int = 4,
    min_correlation: float = 0.45,
) -> tuple[PeerReading, ...]:
    """
    The securities that historically move with the subject,
    and whether they moved with it this time.

    A peer that did NOT follow is the interesting case: the
    move is then specific to the subject, or the peer has
    yet to react.
    """

    sessions = HORIZONS[horizon]
    closes = wide(prices)

    if ticker not in closes:
        return ()

    market = closes[benchmark]
    returns = np.log(closes.drop(columns=[benchmark], errors="ignore")).diff()

    # Co-movement is measured BEFORE the horizon being
    # judged, so a broken relationship does not erase the
    # evidence that it existed.
    history = returns.iloc[-(ESTIMATION_SESSIONS + sessions):-sessions]

    correlations = (
        history.corr()[ticker]
        .drop(ticker)
        .dropna()
        .sort_values(ascending=False)
    )

    subject, _ = abnormal_return_series(closes[ticker].dropna(), market)
    _, subject_z = horizon_zscores(subject, sessions)
    direction = np.sign(subject_z.iloc[-1])

    peers = []

    for peer, correlation in correlations.items():
        if correlation < min_correlation or len(peers) >= limit:
            break

        abnormal, _ = abnormal_return_series(closes[peer].dropna(), market)
        cumulative, z = horizon_zscores(abnormal, sessions)

        if pd.isna(z.iloc[-1]):
            continue

        peers.append(
            PeerReading(
                ticker=peer,
                correlation=float(correlation),
                abnormal_return_pct=float(np.expm1(cumulative.iloc[-1])) * 100,
                z_score=float(z.iloc[-1]),
                followed=bool(
                    np.sign(z.iloc[-1]) == direction
                    and abs(z.iloc[-1]) >= FOLLOWED_Z
                ),
            )
        )

    return tuple(peers)
