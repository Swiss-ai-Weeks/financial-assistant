from __future__ import annotations

from datetime import date
from enum import StrEnum

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


DETECTOR_VERSION = "single-instrument-v1"


class StrategyKind(StrEnum):
    """
    Execution / trading strategy whose assumptions an
    anomaly breaks.

    Each strategy quietly assumes something about the
    market. A detector fires when that assumption stops
    holding, which is exactly when the strategy starts
    losing money and the portfolio manager needs news.
    """

    VWAP = "vwap"
    TWAP = "twap"
    TREND = "trend"
    PAIRS = "pairs"


class SignalKind(StrEnum):
    VOLUME_SPIKE = "volume_spike"
    VWAP_DEVIATION = "vwap_deviation"
    TWAP_DEVIATION = "twap_deviation"
    TREND_CROSS = "trend_cross"
    TREND_WHIPSAW = "trend_whipsaw"


STRATEGY_BY_SIGNAL: dict[SignalKind, StrategyKind] = {
    SignalKind.VOLUME_SPIKE: StrategyKind.VWAP,
    SignalKind.VWAP_DEVIATION: StrategyKind.VWAP,
    SignalKind.TWAP_DEVIATION: StrategyKind.TWAP,
    SignalKind.TREND_CROSS: StrategyKind.TREND,
    SignalKind.TREND_WHIPSAW: StrategyKind.TREND,
}


class SignalAnomaly(BaseModel):
    """
    Point-in-time anomaly on a single instrument.

    Like PairAnomaly, this is an attention event. It is
    not a recommendation and not a causal conclusion.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    anomaly_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)

    kind: SignalKind
    strategy: StrategyKind

    observed_on: date

    # Signed standardised deviation. Positive means
    # above the strategy's reference level.
    z_score: float
    threshold: float = Field(gt=0)

    direction: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    metrics: dict[str, float | int | str] = Field(
        default_factory=dict
    )

    detector_version: str = DETECTOR_VERSION


# -----------------------------------------------------
# Reference series
# -----------------------------------------------------


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise one ticker's OHLCV rows into a frame
    indexed by date.
    """

    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)

    if missing:
        raise ValueError(
            f"prices are missing columns: {sorted(missing)}"
        )

    prepared = frame.copy()
    prepared["date"] = pd.to_datetime(prepared["date"]).dt.normalize()

    return (
        prepared
        .drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .set_index("date")
    )


def typical_price(frame: pd.DataFrame) -> pd.Series:
    return (frame["high"] + frame["low"] + frame["close"]) / 3.0


def rolling_vwap(frame: pd.DataFrame, window: int) -> pd.Series:
    """
    Volume-weighted average of the typical price over
    the trailing window, including the current bar.
    """

    price = typical_price(frame)
    volume = frame["volume"].astype(float)

    traded = (price * volume).rolling(window).sum()
    total = volume.rolling(window).sum()

    return traded / total.replace(0.0, np.nan)


def rolling_twap(frame: pd.DataFrame, window: int) -> pd.Series:
    """
    Time-weighted average: every bar counts equally,
    whatever its volume.
    """

    return typical_price(frame).rolling(window).mean()


def moving_average(frame: pd.DataFrame, window: int) -> pd.Series:
    return frame["close"].rolling(window).mean()


def _trailing_zscore(series: pd.Series, window: int) -> pd.Series:
    """
    Standardise each observation against the window
    strictly BEFORE it.

    shift(1) is the point-in-time boundary: today's
    value never contributes to the baseline it is being
    compared with.
    """

    baseline = series.shift(1)

    mean = baseline.rolling(window).mean()
    std = baseline.rolling(window).std()

    return (series - mean) / std.replace(0.0, np.nan)


def _trailing_sigmas(series: pd.Series, window: int) -> pd.Series:
    """
    Express a deviation in units of its own typical
    size over the window strictly BEFORE it.

    Unlike a z-score the mean is not removed: zero is
    the meaningful reference ("price equals VWAP"), so
    the sign of the result always matches the sign of
    the deviation.
    """

    typical = np.sqrt((series.shift(1) ** 2).rolling(window).mean())

    return series / typical.replace(0.0, np.nan)


def _within(
    series: pd.Series,
    start: str | date | None,
    end: str | date | None,
) -> pd.Series:
    return series.loc[
        (pd.Timestamp(start) if start is not None else None):
        (pd.Timestamp(end) if end is not None else None)
    ]


def _anomaly_id(kind: SignalKind, ticker: str, day: date) -> str:
    return f"{kind.value.upper()}-{ticker}-{day.isoformat()}"


# -----------------------------------------------------
# Detectors
# -----------------------------------------------------


def detect_volume_spikes(
    prices: pd.DataFrame,
    *,
    ticker: str,
    window: int = 20,
    threshold: float = 3.0,
    start: str | date | None = None,
    end: str | date | None = None,
) -> tuple[SignalAnomaly, ...]:
    """
    Abnormal traded volume.

    VWAP execution slices an order along the historical
    volume curve. A volume spike means the curve it was
    scheduled against is no longer the curve being
    traded.
    """

    frame = _prepare(prices)
    volume = frame["volume"].astype(float)

    log_volume = np.log(volume.where(volume > 0))
    z = _trailing_zscore(log_volume, window)

    average = volume.shift(1).rolling(window).mean()

    anomalies = []

    for day, value in _within(z, start, end).dropna().items():
        if value <= threshold:
            continue

        multiple = float(volume.loc[day] / average.loc[day])
        change = float(
            frame["close"].loc[day] / frame["open"].loc[day] - 1.0
        )

        anomalies.append(
            SignalAnomaly(
                anomaly_id=_anomaly_id(
                    SignalKind.VOLUME_SPIKE, ticker, day.date()
                ),
                ticker=ticker,
                kind=SignalKind.VOLUME_SPIKE,
                strategy=StrategyKind.VWAP,
                observed_on=day.date(),
                z_score=float(value),
                threshold=threshold,
                direction="up" if change >= 0 else "down",
                summary=(
                    f"{ticker} traded {multiple:.1f}x its "
                    f"{window}-day average volume "
                    f"(z={value:.2f}) on a "
                    f"{change * 100:+.2f}% session"
                ),
                metrics={
                    "volume": float(volume.loc[day]),
                    "average_volume": float(average.loc[day]),
                    "volume_multiple": multiple,
                    "session_return_pct": change * 100,
                    "window": window,
                },
            )
        )

    return tuple(anomalies)


def detect_vwap_deviations(
    prices: pd.DataFrame,
    *,
    ticker: str,
    window: int = 20,
    baseline: int = 60,
    threshold: float = 2.5,
    start: str | date | None = None,
    end: str | date | None = None,
) -> tuple[SignalAnomaly, ...]:
    """
    Close price stretched away from the rolling VWAP.

    VWAP is the benchmark institutional orders are
    judged against. A stretched close means fills
    around VWAP are now far from where the market
    actually settled.
    """

    frame = _prepare(prices)
    vwap = rolling_vwap(frame, window)

    deviation = frame["close"] / vwap - 1.0
    sigmas = _trailing_sigmas(deviation, baseline)

    anomalies = []

    for day, value in _within(sigmas, start, end).dropna().items():
        if abs(value) <= threshold:
            continue

        gap = float(deviation.loc[day])
        side = "above" if gap > 0 else "below"

        anomalies.append(
            SignalAnomaly(
                anomaly_id=_anomaly_id(
                    SignalKind.VWAP_DEVIATION, ticker, day.date()
                ),
                ticker=ticker,
                kind=SignalKind.VWAP_DEVIATION,
                strategy=StrategyKind.VWAP,
                observed_on=day.date(),
                z_score=float(value),
                threshold=threshold,
                direction=side,
                summary=(
                    f"{ticker} closed {abs(gap) * 100:.2f}% {side} "
                    f"its {window}-day VWAP, {abs(value):.1f}x the "
                    "usual stretch"
                ),
                metrics={
                    "close": float(frame["close"].loc[day]),
                    "vwap": float(vwap.loc[day]),
                    "deviation_pct": gap * 100,
                    "window": window,
                    "baseline": baseline,
                },
            )
        )

    return tuple(anomalies)


def detect_twap_deviations(
    prices: pd.DataFrame,
    *,
    ticker: str,
    horizon: int = 5,
    baseline: int = 60,
    threshold: float = 2.5,
    start: str | date | None = None,
    end: str | date | None = None,
) -> tuple[SignalAnomaly, ...]:
    """
    Drift through a TWAP execution horizon.

    TWAP spreads an order evenly through time and
    ignores volume. It silently assumes the price does
    not drift while the order is being worked.

    The measure is the implementation shortfall of an
    order started `horizon` sessions ago: the average
    price it filled at, relative to the arrival price
    it could have had on day one.
    """

    frame = _prepare(prices)
    twap = rolling_twap(frame, horizon)

    arrival = frame["close"].shift(horizon)
    shortfall = twap / arrival - 1.0

    sigmas = _trailing_sigmas(shortfall, baseline)

    anomalies = []

    for day, value in _within(sigmas, start, end).dropna().items():
        if abs(value) <= threshold:
            continue

        slip = float(shortfall.loc[day])
        side = "above" if slip > 0 else "below"

        anomalies.append(
            SignalAnomaly(
                anomaly_id=_anomaly_id(
                    SignalKind.TWAP_DEVIATION, ticker, day.date()
                ),
                ticker=ticker,
                kind=SignalKind.TWAP_DEVIATION,
                strategy=StrategyKind.TWAP,
                observed_on=day.date(),
                z_score=float(value),
                threshold=threshold,
                direction=side,
                summary=(
                    f"A {horizon}-session TWAP in {ticker} filled "
                    f"{abs(slip) * 100:.2f}% {side} its arrival "
                    f"price, {abs(value):.1f}x the usual drift"
                ),
                metrics={
                    "twap": float(twap.loc[day]),
                    "arrival_price": float(arrival.loc[day]),
                    "shortfall_pct": slip * 100,
                    "horizon": horizon,
                    "baseline": baseline,
                },
            )
        )

    return tuple(anomalies)


def detect_trend_breaks(
    prices: pd.DataFrame,
    *,
    ticker: str,
    fast: int = 7,
    slow: int = 25,
    whipsaw_days: int = 5,
    start: str | date | None = None,
    end: str | date | None = None,
) -> tuple[SignalAnomaly, ...]:
    """
    Moving-average crossovers, and the crossovers that
    failed.

    A cross is the entry/exit trigger of a trend
    following system. A cross that reverses within
    `whipsaw_days` is a whipsaw: the system was pulled
    into a position and stopped straight back out.

    A whipsaw is dated on the day the reversal became
    observable, never on the original cross.
    """

    if fast >= slow:
        raise ValueError("fast window must be shorter than slow")

    frame = _prepare(prices)

    fast_ma = moving_average(frame, fast)
    slow_ma = moving_average(frame, slow)

    spread = (fast_ma - slow_ma).dropna()
    side = np.sign(spread)
    step = spread.diff()
    step_volatility = step.shift(1).rolling(slow).std()

    crosses = side[(side != side.shift(1)) & (side != 0)].iloc[1:]

    anomalies = []
    previous_cross: pd.Timestamp | None = None
    positions = {day: index for index, day in enumerate(spread.index)}

    for day, value in crosses.items():
        bullish = value > 0

        sessions_since = (
            None
            if previous_cross is None
            else positions[day] - positions[previous_cross]
        )

        is_whipsaw = (
            sessions_since is not None
            and sessions_since <= whipsaw_days
        )

        kind = (
            SignalKind.TREND_WHIPSAW
            if is_whipsaw
            else SignalKind.TREND_CROSS
        )

        gap = float(spread.loc[day] / slow_ma.loc[day])

        # The gap is ~0 at a cross by construction, so
        # severity is how violently the averages crossed:
        # the day's move in the gap, in units of its own
        # trailing volatility.
        volatility = step_volatility.loc[day]
        strength = (
            float(step.loc[day] / volatility)
            if np.isfinite(volatility) and volatility > 0
            else 0.0
        )

        label = "golden cross" if bullish else "death cross"

        summary = (
            f"{ticker} MA{fast}/MA{slow} {label}"
            + (
                f" reversing the previous signal after "
                f"{sessions_since} sessions (whipsaw)"
                if is_whipsaw
                else ""
            )
        )

        anomalies.append(
            SignalAnomaly(
                anomaly_id=_anomaly_id(kind, ticker, day.date()),
                ticker=ticker,
                kind=kind,
                strategy=StrategyKind.TREND,
                observed_on=day.date(),
                z_score=strength,
                threshold=1.0,
                direction="bullish" if bullish else "bearish",
                summary=summary,
                metrics={
                    "fast_ma": float(fast_ma.loc[day]),
                    "slow_ma": float(slow_ma.loc[day]),
                    "gap_pct": gap * 100,
                    "fast": fast,
                    "slow": slow,
                    **(
                        {"sessions_since_previous_cross": sessions_since}
                        if sessions_since is not None
                        else {}
                    ),
                },
            )
        )

        previous_cross = day

    selected = {
        day.date()
        for day in _within(crosses, start, end).index
    }

    return tuple(
        anomaly
        for anomaly in anomalies
        if anomaly.observed_on in selected
    )


def detect_signal_anomalies(
    prices: pd.DataFrame,
    *,
    ticker: str,
    start: str | date | None = None,
    end: str | date | None = None,
) -> tuple[SignalAnomaly, ...]:
    """
    Run every single-instrument detector with default
    parameters, most recent first.
    """

    detectors = (
        detect_volume_spikes,
        detect_vwap_deviations,
        detect_twap_deviations,
        detect_trend_breaks,
    )

    anomalies = [
        anomaly
        for detector in detectors
        for anomaly in detector(
            prices,
            ticker=ticker,
            start=start,
            end=end,
        )
    ]

    return tuple(
        sorted(
            anomalies,
            key=lambda anomaly: (
                anomaly.observed_on,
                abs(anomaly.z_score),
            ),
            reverse=True,
        )
    )
