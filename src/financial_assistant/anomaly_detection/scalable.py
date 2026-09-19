from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .cointegration import (
    _prepare_prices,
    engle_granger,
    half_life,
    is_i1,
)

from .models import PairFit


def fit_bounded_pairs(
    prices: pd.DataFrame,
    *,
    start: str | date,
    end: str | date,
    metric: str = "close",
    formation_observations: int = 252,
    corr_floor: float = 0.50,
    alpha_ceiling: float = 0.10,
    max_peers_per_ticker: int = 5,
) -> tuple[PairFit, ...]:
    """
    Scalable formation-window pair fitting.

    This is the large-universe adapter for the same
    pair model used by cointegration.screen_pairs().

    Strategy:

      all securities
          ↓
      pairwise return correlations
          ↓
      top K peers per ticker
          ↓
      exact 252-observation pair alignment
          ↓
      I(1) check
          ↓
      Engle-Granger
          ↓
      PairFit

    Important:
    - Missing dates do NOT remove an entire ticker.
    - The expensive Engle-Granger test is bounded by
      max_peers_per_ticker.
    - alpha_ceiling and corr_floor define the widest
      cache that the UI can subsequently filter.
    """

    if formation_observations <= 2:
        raise ValueError(
            "formation_observations must be > 2"
        )

    if not 0.0 <= corr_floor <= 1.0:
        raise ValueError(
            "corr_floor must be within 0..1"
        )

    if not 0.0 < alpha_ceiling <= 1.0:
        raise ValueError(
            "alpha_ceiling must be within 0..1"
        )

    if max_peers_per_ticker <= 0:
        raise ValueError(
            "max_peers_per_ticker must be > 0"
        )

    wide = (
        _prepare_prices(
            prices,
            metric,
        )
        .loc[start:end]
    )

    if wide.empty:
        return ()

    # Invalid/non-positive prices cannot be logged.
    # Unlike the original small-universe path, one
    # bad observation does not invalidate all columns.
    wide = wide.where(
        wide > 0
    )

    log_px = np.log(wide)

    returns = log_px.diff()

    # Pairwise-complete correlation.
    #
    # This is important for the international universe:
    # US and European exchanges do not share every
    # trading holiday.
    correlations = returns.corr(
        min_periods=(
            formation_observations - 1
        )
    )

    # -------------------------------------------------
    # Build a bounded peer graph.
    #
    # Each security contributes at most K highly
    # correlated peers. A pair may be selected from
    # either direction, hence the set/dict.
    # -------------------------------------------------

    candidate_correlations: dict[
        tuple[str, str],
        float,
    ] = {}

    for ticker in correlations.columns:
        peers = (
            correlations[ticker]
            .drop(
                labels=[ticker],
                errors="ignore",
            )
            .dropna()
        )

        peers = peers[
            peers >= corr_floor
        ].nlargest(
            max_peers_per_ticker
        )

        for peer, correlation in peers.items():
            pair = tuple(
                sorted(
                    (
                        str(ticker),
                        str(peer),
                    )
                )
            )

            existing = (
                candidate_correlations.get(
                    pair
                )
            )

            value = float(
                correlation
            )

            if (
                existing is None
                or value > existing
            ):
                candidate_correlations[
                    pair
                ] = value

    # -------------------------------------------------
    # Cache the I(1) precondition per security.
    #
    # The original algorithm repeats this inside every
    # pair test. With thousands of securities that
    # becomes unnecessarily expensive.
    # -------------------------------------------------

    involved_tickers = {
        ticker
        for pair
        in candidate_correlations
        for ticker in pair
    }

    i1_status: dict[str, bool] = {}

    for ticker in involved_tickers:
        series = (
            log_px[ticker]
            .dropna()
            .tail(
                formation_observations
            )
        )

        if (
            len(series)
            < formation_observations
        ):
            i1_status[ticker] = False
            continue

        try:
            i1_status[ticker] = is_i1(
                series
            )
        except (
            ValueError,
            np.linalg.LinAlgError,
        ):
            i1_status[ticker] = False

    fits: list[PairFit] = []

    for (
        ticker_a,
        ticker_b,
    ), _ in candidate_correlations.items():

        if not (
            i1_status.get(
                ticker_a,
                False,
            )
            and i1_status.get(
                ticker_b,
                False,
            )
        ):
            continue

        # Pairwise alignment avoids the global
        # complete-case problem.
        aligned = (
            log_px[
                [
                    ticker_a,
                    ticker_b,
                ]
            ]
            .dropna()
            .tail(
                formation_observations
            )
        )

        if (
            len(aligned)
            < formation_observations
        ):
            continue

        # Recalculate correlation on the exact
        # observations used for the pair fit.
        exact_corr = float(
            aligned
            .diff()
            .dropna()
            .corr()
            .iloc[0, 1]
        )

        if (
            not np.isfinite(
                exact_corr
            )
            or exact_corr < corr_floor
        ):
            continue

        result = engle_granger(
            aligned[ticker_a],
            aligned[ticker_b],
            check_i1=False,
            alpha=alpha_ceiling,
        )

        if (
            result is None
            or not result[
                "cointegrated"
            ]
        ):
            continue

        spread = result[
            "spread"
        ]

        spread_std = float(
            spread.std()
        )

        if (
            not np.isfinite(
                spread_std
            )
            or spread_std <= 0
        ):
            continue

        try:
            hl = half_life(
                spread
            )
        except (
            ValueError,
            np.linalg.LinAlgError,
        ):
            hl = float("inf")

        fits.append(
            PairFit(
                ticker_a=ticker_a,
                ticker_b=ticker_b,

                metric=metric,

                formation_start=(
                    aligned
                    .index
                    .min()
                    .date()
                ),

                formation_end=(
                    aligned
                    .index
                    .max()
                    .date()
                ),

                correlation=exact_corr,

                const=result[
                    "const"
                ],

                beta=result[
                    "beta"
                ],

                adf_stat=result[
                    "adf_stat"
                ],

                pvalue=result[
                    "pvalue"
                ],

                adf_lags=result[
                    "lags"
                ],

                nobs=result[
                    "nobs"
                ],

                half_life_days=(
                    None
                    if not np.isfinite(
                        hl
                    )
                    else float(hl)
                ),

                spread_mean=float(
                    spread.mean()
                ),

                spread_std=(
                    spread_std
                ),
            )
        )

    return tuple(
        sorted(
            fits,
            key=lambda fit: (
                fit.pvalue,
                -fit.correlation,
                fit.ticker_a,
                fit.ticker_b,
            ),
        )
    )
