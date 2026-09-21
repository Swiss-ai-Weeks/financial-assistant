from __future__ import annotations

from datetime import date, timedelta

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


def fit_universe_pairs(
    prices: pd.DataFrame,
    universe: pd.DataFrame,
    *,
    as_of: str | date,
    formation_observations: int = 252,
    metric: str = "close",
    corr_floor: float = 0.50,
    alpha_ceiling: float = 0.10,
    max_peers_per_ticker: int = 5,
) -> tuple[tuple[PairFit, ...], list[dict]]:
    """Shared live-cache/historical policy, with a strict formation cutoff.

    The calendar envelope is for peer screening only. Each PairFit records
    its own final exact N pairwise-complete formation observations.
    """
    as_of = pd.Timestamp(as_of).normalize()
    formation_start = as_of.date() - timedelta(days=450)
    formation_end = as_of.date() - timedelta(days=1)
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame = frame.loc[frame["date"] < as_of]
    mapped = universe.loc[universe["mapping_status"] == "mapped"]
    all_fits = []
    summaries = []
    for (universe_name, currency), group in mapped.groupby(
        ["universe", "currency"], dropna=False
    ):
        tickers = set(group["yahoo_ticker"].dropna().astype(str))
        subset = frame.loc[frame["ticker"].isin(tickers)].copy()
        available = int(subset["ticker"].nunique())
        if available < 2:
            continue
        fits = fit_bounded_pairs(
            subset, start=formation_start, end=formation_end, metric=metric,
            formation_observations=formation_observations,
            corr_floor=corr_floor, alpha_ceiling=alpha_ceiling,
            max_peers_per_ticker=max_peers_per_ticker,
        )
        summaries.append(dict(group=f"{universe_name}/{currency}",
                              tickers=available, fits=len(fits)))
        all_fits.extend(fits)
    return tuple(all_fits), summaries


def fit_large_universe(
    prices: pd.DataFrame,
    *,
    start: str | date,
    end: str | date,
    metric: str = "close",
    corr_min: float = 0.70,
    alpha: float = 0.05,
    focus: frozenset[str] | None = None,
    sectors: dict[str, str] | None = None,
    corr_min_same_sector: float | None = None,
    groups: dict[str, str] | None = None,
    formation_observations: int = 252,
    max_peers_per_ticker: int = 5,
) -> tuple[PairFit, ...]:
    """
    cointegration.fit_pairs for a universe of thousands.

    The desk's own fitter tests every pair above the
    correlation bar and needs every security to share one
    calendar. With 3,000 names across Europe and the US that
    is millions of pairs and an empty calendar. Here:

      - correlations are pairwise-complete, so exchanges with
        different holidays can coexist;
      - each security keeps only its `max_peers_per_ticker`
        most correlated peers, which bounds the number of
        Engle-Granger tests, and with it the false positives;
      - `groups` (ticker -> group) keeps a pair inside one
        universe and currency: a EUR/USD pair would be a bet
        on the exchange rate, not on the two companies;
      - with `focus`, only the peers of those tickers are
        looked for, so a holding costs one row of the
        correlation matrix instead of all of it.

    Thresholds mean what they mean in fit_pairs: same-sector
    pairs are admitted at `corr_min_same_sector`, all others
    at `corr_min`, and both orderings of a pair are tested.
    """

    if formation_observations <= 2:
        raise ValueError("formation_observations must be > 2")

    wide = _prepare_prices(prices, metric).loc[start:end]

    if wide.empty:
        return ()

    wide = wide.where(wide > 0)

    # A security needs the whole formation window to be fitted
    # at all; dropping the rest first makes everything cheaper.
    wide = wide.loc[:, wide.notna().sum() >= formation_observations]

    if wide.shape[1] < 2:
        return ()

    log_px = np.log(wide)
    returns = log_px.diff()

    floor = min(
        corr_min,
        corr_min_same_sector if corr_min_same_sector is not None else corr_min,
    )

    def required(ticker_a: str, ticker_b: str) -> float:
        same_sector = (
            sectors is not None
            and corr_min_same_sector is not None
            and sectors.get(ticker_a) is not None
            and sectors.get(ticker_a) == sectors.get(ticker_b)
        )

        return corr_min_same_sector if same_sector else corr_min

    def same_group(ticker_a: str, ticker_b: str) -> bool:
        if groups is None:
            return True

        # Securities outside the catalogue (a holding found by
        # search) are free to pair with anything.
        group_a, group_b = groups.get(ticker_a), groups.get(ticker_b)

        return group_a is None or group_b is None or group_a == group_b

    subjects = (
        [t for t in wide.columns if t in focus]
        if focus is not None
        else list(wide.columns)
    )

    min_periods = formation_observations - 1

    if focus is not None and len(subjects) <= 64:
        correlations = pd.DataFrame(
            {
                subject: returns.corrwith(returns[subject])
                for subject in subjects
            }
        )
        counts = returns.notna().astype(int).T @ returns[subjects].notna().astype(int)
        correlations = correlations.where(counts >= min_periods)
    else:
        correlations = returns.corr(min_periods=min_periods)[subjects]

    candidates: dict[tuple[str, str], float] = {}

    for subject in subjects:
        peers = correlations[subject].drop(labels=[subject], errors="ignore").dropna()
        peers = peers[peers >= floor]

        peers = peers[
            [
                same_group(subject, peer)
                and value >= required(subject, peer)
                for peer, value in peers.items()
            ]
        ].nlargest(max_peers_per_ticker)

        for peer, value in peers.items():
            pair = tuple(sorted((str(subject), str(peer))))
            candidates[pair] = max(candidates.get(pair, -1.0), float(value))

    i1: dict[str, bool] = {}

    def integrated(ticker: str) -> bool:
        if ticker not in i1:
            series = log_px[ticker].dropna().tail(formation_observations)

            try:
                i1[ticker] = len(series) >= formation_observations and is_i1(series)
            except (ValueError, np.linalg.LinAlgError):
                i1[ticker] = False

        return i1[ticker]

    fits: list[PairFit] = []

    for first, second in candidates:
        if not (integrated(first) and integrated(second)):
            continue

        aligned = log_px[[first, second]].dropna().tail(formation_observations)

        if len(aligned) < formation_observations:
            continue

        exact = float(aligned.diff().dropna().corr().iloc[0, 1])

        if not np.isfinite(exact) or exact < required(first, second):
            continue

        orderings = []

        for dependent, regressor in ((first, second), (second, first)):
            try:
                outcome = engle_granger(
                    aligned[dependent],
                    aligned[regressor],
                    check_i1=False,
                    alpha=alpha,
                )
            except (ValueError, np.linalg.LinAlgError):
                continue

            if outcome is not None and outcome["cointegrated"]:
                orderings.append((dependent, regressor, outcome))

        if not orderings:
            continue

        ticker_a, ticker_b, result = min(
            orderings,
            key=lambda item: item[2]["pvalue"],
        )

        spread = result["spread"]
        spread_std = float(spread.std())

        if not np.isfinite(spread_std) or spread_std <= 0:
            continue

        try:
            hl = half_life(spread)
        except (ValueError, np.linalg.LinAlgError):
            hl = float("inf")

        fits.append(
            PairFit(
                ticker_a=ticker_a,
                ticker_b=ticker_b,
                metric=metric,
                formation_start=aligned.index.min().date(),
                formation_end=aligned.index.max().date(),
                correlation=exact,
                const=result["const"],
                beta=result["beta"],
                adf_stat=result["adf_stat"],
                pvalue=result["pvalue"],
                adf_lags=result["lags"],
                nobs=result["nobs"],
                half_life_days=None if not np.isfinite(hl) else float(hl),
                spread_mean=float(spread.mean()),
                spread_std=spread_std,
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
