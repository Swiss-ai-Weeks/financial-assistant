from __future__ import annotations

import itertools
from datetime import date

import numpy as np
import pandas as pd
import statsmodels.api as sm

from statsmodels.tsa.adfvalues import (
    mackinnonp,
)

from statsmodels.tsa.stattools import (
    adfuller,
)

from .models import (
    PairAnomaly,
    PairFit,
)


def _prepare_prices(
    prices: pd.DataFrame,
    metric: str,
) -> pd.DataFrame:
    """
    Convert the long price table

        date | ticker | close

    into a wide date x ticker matrix.
    """

    required = {
        "date",
        "ticker",
        metric,
    }

    missing = (
        required - set(prices.columns)
    )

    if missing:
        raise ValueError(
            "Missing required price columns: "
            + ", ".join(sorted(missing))
        )

    frame = prices.copy()

    frame["date"] = pd.to_datetime(
        frame["date"]
    )

    return frame.pivot(
        index="date",
        columns="ticker",
        values=metric,
    ).sort_index()


def is_i1(
    series: pd.Series,
    alpha: float = 0.05,
) -> bool:
    """
    True when a series appears I(1):

    - unit root is not rejected in levels
    - unit root is rejected after first differencing

    This is the same precondition used by the
    original research notebook.
    """

    clean = (
        series
        .dropna()
        .astype(float)
    )

    level_pvalue = adfuller(
        clean,
        regression="c",
        result_object=False,
    )[1]

    diff_pvalue = adfuller(
        clean.diff().dropna(),
        regression="c",
        result_object=False,
    )[1]

    return (
        level_pvalue > alpha
        and diff_pvalue <= alpha
    )


def half_life(
    spread: pd.Series,
) -> float:
    """
    Estimated mean-reversion half-life of a spread,
    expressed in trading days.
    """

    clean = spread.dropna()

    lag = clean.shift(1).dropna()
    delta = clean.diff().dropna()

    aligned_lag = lag.loc[
        delta.index
    ]

    beta = (
        sm.OLS(
            delta,
            sm.add_constant(
                aligned_lag
            ),
        )
        .fit()
        .params
        .iloc[1]
    )

    if beta >= 0:
        return float("inf")

    return float(
        -np.log(2) / beta
    )


def engle_granger(
    y: pd.Series,
    x: pd.Series,
    *,
    check_i1: bool = True,
    alpha: float = 0.05,
) -> dict | None:
    """
    Engle-Granger two-step cointegration test.

    y and x should normally be log-price series.

    Returns None when the I(1) precondition fails.
    """

    aligned = pd.concat(
        [
            y.rename("y"),
            x.rename("x"),
        ],
        axis=1,
    ).dropna()

    y_clean = aligned["y"]
    x_clean = aligned["x"]

    if (
        check_i1
        and not (
            is_i1(y_clean)
            and is_i1(x_clean)
        )
    ):
        return None

    # Step 1:
    #
    # y = const + beta*x + spread
    fit = sm.OLS(
        y_clean,
        sm.add_constant(x_clean),
    ).fit()

    spread = fit.resid

    # Step 2:
    #
    # ADF on estimated residuals.
    (
        adf_stat,
        _,
        lags,
        nobs,
        _,
        _,
    ) = adfuller(
        spread,
        regression="n",
        autolag="AIC",
        result_object=False,
    )

    # Because these residuals were estimated rather
    # than directly observed, use MacKinnon's
    # cointegration distribution for N=2.
    pvalue = mackinnonp(
        adf_stat,
        regression="c",
        N=2,
    )

    return {
        "beta": float(
            fit.params.iloc[1]
        ),
        "const": float(
            fit.params.iloc[0]
        ),
        "adf_stat": float(
            adf_stat
        ),
        "pvalue": float(
            pvalue
        ),
        "lags": int(lags),
        "nobs": int(nobs),
        "cointegrated": (
            pvalue < alpha
        ),
        "spread": spread,
    }


def screen_pairs(
    prices: pd.DataFrame,
    *,
    metric: str = "close",
    start: str | date | None = None,
    end: str | date | None = None,
    corr_min: float = 0.70,
    alpha: float = 0.01,
    focus: frozenset[str] | None = None,
    sectors: dict[str, str] | None = None,
    corr_min_same_sector: float | None = None,
) -> tuple[PairFit, ...]:
    """
    Screen all eligible pairs using only the
    formation window.

    The return-correlation filter reduces the number
    of pairwise Engle-Granger tests.

    Every test is a chance of a false positive, so the
    correlation filter is also the guard against flukes.
    Two names with a shared economic driver deserve a
    looser bar than two unrelated ones: with `sectors`
    and `corr_min_same_sector`, same-sector pairs are
    admitted at the looser threshold while cross-sector
    pairs still need `corr_min`.

    When `focus` is given, only pairs with at least
    one leg in it are tested. A portfolio only needs
    the relationships that involve its own holdings.
    """

    wide = _prepare_prices(
        prices,
        metric,
    )

    wide = (
        wide
        .loc[start:end]
        .dropna(axis=1)
    )

    if wide.empty:
        return ()

    if (wide <= 0).any().any():
        raise ValueError(
            "Cointegration detector requires "
            "strictly positive prices before "
            "taking logarithms."
        )

    log_px = np.log(wide)

    correlations = (
        log_px
        .diff()
        .corr()
    )

    def required_correlation(
        ticker_a: str,
        ticker_b: str,
    ) -> float:
        same_sector = (
            sectors is not None
            and corr_min_same_sector is not None
            and sectors.get(ticker_a) is not None
            and sectors.get(ticker_a)
            == sectors.get(ticker_b)
        )

        return (
            corr_min_same_sector
            if same_sector
            else corr_min
        )

    candidates = [
        (ticker_a, ticker_b)
        for ticker_a, ticker_b
        in itertools.combinations(
            wide.columns,
            2,
        )
        if (
            correlations.loc[
                ticker_a,
                ticker_b,
            ]
            >= required_correlation(
                ticker_a,
                ticker_b,
            )
        )
        and (
            focus is None
            or ticker_a in focus
            or ticker_b in focus
        )
    ]

    fits: list[PairFit] = []

    formation_start = (
        log_px.index.min().date()
    )

    formation_end = (
        log_px.index.max().date()
    )

    for first, second in candidates:
        # Engle-Granger is not symmetric: regressing A on B
        # and B on A give different residuals and can give
        # different verdicts. Both orderings are tested and
        # the stronger relationship is kept, with ticker_a
        # as its dependent leg.
        orderings = [
            (dependent, regressor, outcome)
            for dependent, regressor in (
                (first, second),
                (second, first),
            )
            if (
                outcome := engle_granger(
                    log_px[dependent],
                    log_px[regressor],
                    alpha=alpha,
                )
            )
            is not None
            and outcome["cointegrated"]
        ]

        if not orderings:
            continue

        ticker_a, ticker_b, result = min(
            orderings,
            key=lambda ordering: ordering[2]["pvalue"],
        )

        spread = result["spread"]

        spread_std = float(
            spread.std()
        )

        if (
            not np.isfinite(spread_std)
            or spread_std <= 0
        ):
            continue

        hl = half_life(
            spread
        )

        fits.append(
            PairFit(
                ticker_a=ticker_a,
                ticker_b=ticker_b,
                metric=metric,

                formation_start=(
                    formation_start
                ),
                formation_end=(
                    formation_end
                ),

                correlation=float(
                    correlations.loc[
                        ticker_a,
                        ticker_b,
                    ]
                ),

                const=result["const"],
                beta=result["beta"],

                adf_stat=(
                    result["adf_stat"]
                ),
                pvalue=result["pvalue"],

                adf_lags=result["lags"],
                nobs=result["nobs"],

                half_life_days=(
                    None
                    if not np.isfinite(hl)
                    else float(hl)
                ),

                spread_mean=float(
                    spread.mean()
                ),
                spread_std=spread_std,
            )
        )

    return tuple(
        sorted(
            fits,
            key=lambda fit: fit.pvalue,
        )
    )


def fit_pairs(
    prices: pd.DataFrame,
    *,
    start: str | date,
    end: str | date,
    metric: str = "close",
    corr_min: float = 0.70,
    alpha: float = 0.01,
    focus: frozenset[str] | None = None,
    sectors: dict[str, str] | None = None,
    corr_min_same_sector: float | None = None,
) -> tuple[PairFit, ...]:
    """
    Explicit alias for formation-window fitting.

    Kept because it mirrors the notebook workflow:

        fit_pairs(...)
        monitor_pairs(...)
    """

    return screen_pairs(
        prices,
        metric=metric,
        start=start,
        end=end,
        corr_min=corr_min,
        alpha=alpha,
        focus=focus,
        sectors=sectors,
        corr_min_same_sector=corr_min_same_sector,
    )


def monitor_pairs(
    prices: pd.DataFrame,
    fits: tuple[PairFit, ...],
    *,
    start: str | date,
    end: str | date,
    entry: float = 2.0,
) -> tuple[
    pd.DataFrame,
    tuple[PairAnomaly, ...],
]:
    """
    Monitor frozen pair relationships.

    CRITICAL POINT-IN-TIME RULE:

    beta, const, spread_mean and spread_std all come
    from PairFit and therefore from the formation
    window only.

    Nothing is re-estimated from monitoring data.
    """

    if entry <= 0:
        raise ValueError(
            "entry threshold must be > 0"
        )

    wide = _prepare_prices(
        prices,
        "close",
    )

    zscores: dict[str, pd.Series] = {}
    anomalies: list[PairAnomaly] = []

    for fit in fits:
        metric_wide = (
            wide
            if fit.metric == "close"
            else _prepare_prices(
                prices,
                fit.metric,
            )
        )

        live = metric_wide.loc[
            start:end
        ]

        if (
            fit.ticker_a
            not in live.columns
            or fit.ticker_b
            not in live.columns
        ):
            continue

        pair_live = live[
            [
                fit.ticker_a,
                fit.ticker_b,
            ]
        ].dropna()

        if pair_live.empty:
            continue

        if (pair_live <= 0).any().any():
            continue

        log_a = np.log(
            pair_live[fit.ticker_a]
        )

        log_b = np.log(
            pair_live[fit.ticker_b]
        )

        spread = (
            log_a
            - fit.const
            - fit.beta * log_b
        )

        z = (
            spread - fit.spread_mean
        ) / fit.spread_std

        pair_name = (
            f"{fit.ticker_a}/"
            f"{fit.ticker_b}"
        )

        zscores[pair_name] = z

        flags = z[
            z.abs() > entry
        ]

        if flags.empty:
            continue

        z_last = float(
            z.iloc[-1]
        )

        direction = (
            "a_above_equilibrium"
            if z_last > 0
            else "a_below_equilibrium"
        )

        monitoring_start = (
            pair_live.index.min().date()
        )

        monitoring_end = (
            pair_live.index.max().date()
        )

        anomaly_id = (
            "PAIR-"
            f"{fit.ticker_a}-"
            f"{fit.ticker_b}-"
            f"{monitoring_end.isoformat()}"
        )

        anomalies.append(
            PairAnomaly(
                anomaly_id=anomaly_id,

                ticker_a=fit.ticker_a,
                ticker_b=fit.ticker_b,

                metric=fit.metric,

                monitoring_start=(
                    monitoring_start
                ),
                monitoring_end=(
                    monitoring_end
                ),

                first_flag=(
                    flags.index[0].date()
                ),

                threshold=entry,

                n_days_flagged=(
                    len(flags)
                ),

                z_score=z_last,

                max_abs_z=float(
                    z.abs().max()
                ),

                peak_date=(
                    z.abs().idxmax().date()
                ),

                relative_direction=(
                    direction
                ),

                beta=fit.beta,
                const=fit.const,

                formation_start=(
                    fit.formation_start
                ),
                formation_end=(
                    fit.formation_end
                ),
            )
        )

    zscore_frame = pd.DataFrame(
        zscores
    )

    anomalies.sort(
        key=lambda anomaly:
            anomaly.max_abs_z,
        reverse=True,
    )

    return (
        zscore_frame,
        tuple(anomalies),
    )
