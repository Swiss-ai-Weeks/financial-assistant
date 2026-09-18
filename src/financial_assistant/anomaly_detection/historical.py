from __future__ import annotations

from datetime import date

import pandas as pd
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from .cointegration import (
    fit_pairs,
    monitor_pairs,
)
from .models import (
    PairAnomaly,
    PairFit,
)


DETECTOR_VERSION = "historical-pair-v1"


class HistoricalPairSignal(BaseModel):
    """
    A pair anomaly observed from the information
    available at one historical point in time.

    The PairFit contains the relationship known before
    `as_of`.

    The PairAnomaly contains the deviation observed
    exactly on `as_of`.

    Future prices are deliberately not part of this
    object. Forward outcomes belong to the simulation
    layer.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    signal_id: str = Field(
        min_length=1
    )

    as_of: date

    fit: PairFit
    anomaly: PairAnomaly

    formation_observations: int = Field(
        gt=1
    )

    corr_min: float
    alpha: float
    entry: float

    detector_version: str = (
        DETECTOR_VERSION
    )


def scan_pairs_as_of(
    prices: pd.DataFrame,
    *,
    as_of: str | date,
    formation_observations: int = 252,
    metric: str = "close",
    corr_min: float = 0.70,
    alpha: float = 0.01,
    entry: float = 2.0,
) -> tuple[
    HistoricalPairSignal,
    ...
]:
    """
    Reconstruct the pair-anomaly state at one date.

    CRITICAL POINT-IN-TIME GUARANTEE:

    Prices after `as_of` are removed before any
    fitting or monitoring operation.

    Formation uses the final N distinct observations
    strictly BEFORE `as_of`.

    Monitoring is performed ONLY on `as_of`.

    Therefore future prices cannot affect:
      - pair selection
      - correlation
      - Engle-Granger fitting
      - beta / const
      - spread distribution
      - anomaly detection
    """

    if formation_observations <= 1:
        raise ValueError(
            "formation_observations "
            "must be greater than 1."
        )

    if "date" not in prices.columns:
        raise ValueError(
            "prices must contain a date column."
        )

    as_of_ts = pd.Timestamp(
        as_of
    ).normalize()

    as_of_date = as_of_ts.date()

    frame = prices.copy()

    frame["date"] = (
        pd.to_datetime(
            frame["date"]
        )
        .dt
        .normalize()
    )

    # -------------------------------------------------
    # Point-in-time boundary.
    #
    # Nothing below this line can see observations
    # after the requested historical date.
    # -------------------------------------------------

    available = frame.loc[
        frame["date"] <= as_of_ts
    ].copy()

    if available.empty:
        raise ValueError(
            "No market observations exist "
            f"on or before {as_of_date}."
        )

    if not (
        available["date"]
        == as_of_ts
    ).any():
        raise ValueError(
            "No market observations exist "
            f"on {as_of_date}."
        )

    formation_dates = (
        available.loc[
            available["date"]
            < as_of_ts,
            "date",
        ]
        .drop_duplicates()
        .sort_values()
    )

    if (
        len(formation_dates)
        < formation_observations
    ):
        raise ValueError(
            "Insufficient formation history: "
            f"need {formation_observations} "
            "observations strictly before "
            f"{as_of_date}, found "
            f"{len(formation_dates)}."
        )

    selected_dates = (
        formation_dates
        .iloc[
            -formation_observations:
        ]
    )

    formation_start = (
        selected_dates
        .iloc[0]
        .date()
    )

    formation_end = (
        selected_dates
        .iloc[-1]
        .date()
    )

    # -------------------------------------------------
    # Fit relationships using only information
    # strictly before the time-travel date.
    # -------------------------------------------------

    fits = fit_pairs(
        available,
        start=formation_start,
        end=formation_end,
        metric=metric,
        corr_min=corr_min,
        alpha=alpha,
    )

    if not fits:
        return ()

    # -------------------------------------------------
    # Observe each frozen relationship exactly on D.
    #
    # start=end is intentional. We want:
    #
    #   "Which pairs are anomalous ON this date?"
    #
    # rather than:
    #
    #   "Which pairs were anomalous at any point in
    #    this interval?"
    # -------------------------------------------------

    _, anomalies = monitor_pairs(
        available,
        fits,
        start=as_of_date,
        end=as_of_date,
        entry=entry,
    )

    fit_by_pair = {
        (
            fit.ticker_a,
            fit.ticker_b,
        ): fit
        for fit in fits
    }

    signals: list[
        HistoricalPairSignal
    ] = []

    for anomaly in anomalies:
        pair = (
            anomaly.ticker_a,
            anomaly.ticker_b,
        )

        fit = fit_by_pair.get(
            pair
        )

        if fit is None:
            raise RuntimeError(
                "Historical anomaly references "
                "a pair that was not present in "
                "the frozen formation fits: "
                f"{pair}"
            )

        signal_id = (
            "HPS-"
            f"{anomaly.ticker_a}-"
            f"{anomaly.ticker_b}-"
            f"{as_of_date.isoformat()}"
        )

        signals.append(
            HistoricalPairSignal(
                signal_id=signal_id,
                as_of=as_of_date,

                fit=fit,
                anomaly=anomaly,

                formation_observations=(
                    formation_observations
                ),

                corr_min=corr_min,
                alpha=alpha,
                entry=entry,
            )
        )

    # Most extreme current deviations first.
    return tuple(
        sorted(
            signals,
            key=lambda signal: (
                -abs(
                    signal
                    .anomaly
                    .z_score
                ),
                signal.fit.ticker_a,
                signal.fit.ticker_b,
            ),
        )
    )
