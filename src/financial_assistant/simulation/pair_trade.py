from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from financial_assistant.anomaly_detection.historical import (
    HistoricalPairSignal,
)


SIMULATOR_VERSION = "pair-forward-v1"


class ForwardReturnPoint(BaseModel):
    """
    Historical outcome measured a fixed number of
    common trading observations after entry.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    horizon_observations: int = Field(
        gt=0
    )

    date: date

    return_pct: float
    pnl: float


class PairForwardSimulation(BaseModel):
    """
    Hindsight-only simulation of a mechanical
    mean-reversion position.

    This object deliberately lives outside the
    historical anomaly signal because its calculations
    use prices that were not available at `as_of`.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    simulation_id: str = Field(
        min_length=1
    )

    signal_id: str = Field(
        min_length=1
    )

    as_of: date

    ticker_a: str
    ticker_b: str

    entry_date: date
    entry_metric: str

    gross_capital: float = Field(
        gt=0
    )

    signal_z_score: float
    beta: float

    strategy_direction: str

    # Signed fractions of gross capital.
    #
    # Example:
    #
    #   weight_a = -0.5
    #   weight_b = +0.5
    #
    # means short A and long B.
    weight_a: float
    weight_b: float

    notional_a: float
    notional_b: float

    forward_returns: tuple[
        ForwardReturnPoint,
        ...
    ]

    latest_date: date

    return_to_latest_pct: float
    pnl_to_latest: float

    # Drawdown of the simulated cumulative P&L
    # relative to its previous peak, expressed as a
    # percentage of initial gross capital.
    max_drawdown_pct: float

    # First future date on which the frozen spread
    # crosses equilibrium, if it does.
    mean_reversion_date: date | None = None

    mean_reversion_return_pct: (
        float | None
    ) = None

    transaction_cost_bps: float = 0.0

    simulator_version: str = (
        SIMULATOR_VERSION
    )


def _wide_prices(
    prices: pd.DataFrame,
    *,
    metric: str,
    ticker_a: str,
    ticker_b: str,
) -> pd.DataFrame:
    required = {
        "date",
        "ticker",
        metric,
    }

    missing = (
        required
        - set(prices.columns)
    )

    if missing:
        raise ValueError(
            "Missing required price columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    frame = prices.copy()

    frame["date"] = (
        pd.to_datetime(
            frame["date"]
        )
        .dt
        .normalize()
    )

    wide = (
        frame
        .pivot(
            index="date",
            columns="ticker",
            values=metric,
        )
        .sort_index()
    )

    if (
        ticker_a not in wide.columns
        or ticker_b not in wide.columns
    ):
        raise ValueError(
            "Prices do not contain both "
            "signal tickers."
        )

    pair = (
        wide[
            [
                ticker_a,
                ticker_b,
            ]
        ]
        .dropna()
        .astype(float)
    )

    if (
        not pair.empty
        and (pair <= 0).any().any()
    ):
        raise ValueError(
            "Pair simulation requires "
            "strictly positive prices."
        )

    return pair


def simulate_pair_forward(
    signal: HistoricalPairSignal,
    prices: pd.DataFrame,
    *,
    gross_capital: float = 10_000.0,
    horizons: tuple[int, ...] = (
        1,
        5,
        10,
        20,
    ),
    transaction_cost_bps: float = 0.0,
) -> PairForwardSimulation:
    """
    Fast-forward a historical pair anomaly.

    INFORMATION BOUNDARY
    --------------------

    Detection:
        uses prices <= signal.as_of

    Simulation:
        uses prices > signal.as_of

    Entry occurs on the first common price observation
    AFTER the signal date.

    With daily close-only data this therefore means the
    next common closing observation, avoiding an
    impossible same-close fill after observing that
    close.

    When an OHLCV market-data adapter is added later,
    the same simulation layer can be extended to enter
    at the next common open.
    """

    if gross_capital <= 0:
        raise ValueError(
            "gross_capital must be > 0."
        )

    if transaction_cost_bps < 0:
        raise ValueError(
            "transaction_cost_bps "
            "must be >= 0."
        )

    if any(
        horizon <= 0
        for horizon in horizons
    ):
        raise ValueError(
            "All horizons must be > 0."
        )

    fit = signal.fit
    anomaly = signal.anomaly

    pair = _wide_prices(
        prices,
        metric=fit.metric,
        ticker_a=fit.ticker_a,
        ticker_b=fit.ticker_b,
    )

    as_of_ts = pd.Timestamp(
        signal.as_of
    ).normalize()

    # -------------------------------------------------
    # Hindsight boundary.
    #
    # Unlike the detector, the simulator intentionally
    # sees ONLY observations after the historical
    # signal date.
    # -------------------------------------------------

    future = pair.loc[
        pair.index > as_of_ts
    ]

    if future.empty:
        raise ValueError(
            "No future common price observations "
            "exist after the signal date."
        )

    entry_date_ts = (
        future.index[0]
    )

    entry_prices = future.loc[
        entry_date_ts
    ]

    # -------------------------------------------------
    # Mechanical spread position.
    #
    # spread = log(A) - const - beta*log(B)
    #
    # Positive spread:
    #     short spread
    #     raw position = (-1, +beta)
    #
    # Negative spread:
    #     long spread
    #     raw position = (+1, -beta)
    # -------------------------------------------------

    if anomaly.z_score > 0:
        raw_a = -1.0
        raw_b = float(fit.beta)

        strategy_direction = (
            "short_spread"
        )

    elif anomaly.z_score < 0:
        raw_a = 1.0
        raw_b = -float(fit.beta)

        strategy_direction = (
            "long_spread"
        )

    else:
        raise ValueError(
            "Cannot construct a mean-reversion "
            "position from a zero z-score."
        )

    gross_weight = (
        abs(raw_a)
        + abs(raw_b)
    )

    if (
        not np.isfinite(
            gross_weight
        )
        or gross_weight <= 0
    ):
        raise ValueError(
            "Invalid hedge ratio for "
            "simulation."
        )

    weight_a = (
        raw_a
        / gross_weight
    )

    weight_b = (
        raw_b
        / gross_weight
    )

    notional_a = (
        gross_capital
        * weight_a
    )

    notional_b = (
        gross_capital
        * weight_b
    )

    # -------------------------------------------------
    # Historical P&L path.
    #
    # Signed dollar weights are fixed at entry.
    # This is deliberately a simple, transparent
    # simulation rather than a rebalanced strategy.
    # -------------------------------------------------

    return_a = (
        future[fit.ticker_a]
        / float(
            entry_prices[
                fit.ticker_a
            ]
        )
        - 1.0
    )

    return_b = (
        future[fit.ticker_b]
        / float(
            entry_prices[
                fit.ticker_b
            ]
        )
        - 1.0
    )

    portfolio_return = (
        weight_a * return_a
        + weight_b * return_b
    )

    # One-time illustrative cost applied to initial
    # gross exposure. Default remains zero until we
    # explicitly model slippage/borrow/fees.
    cost_decimal = (
        transaction_cost_bps
        / 10_000.0
    )

    portfolio_return = (
        portfolio_return
        - cost_decimal
    )

    # Entry itself should represent zero market P&L.
    # If transaction costs are non-zero, the path begins
    # with that explicit cost.
    forward_points: list[
        ForwardReturnPoint
    ] = []

    for horizon in sorted(
        set(horizons)
    ):
        target_index = horizon

        if target_index >= len(
            portfolio_return
        ):
            continue

        target_date = (
            portfolio_return
            .index[target_index]
        )

        value = float(
            portfolio_return.iloc[
                target_index
            ]
        )

        forward_points.append(
            ForwardReturnPoint(
                horizon_observations=(
                    horizon
                ),

                date=(
                    target_date.date()
                ),

                return_pct=(
                    value * 100.0
                ),

                pnl=(
                    value
                    * gross_capital
                ),
            )
        )

    latest_value = float(
        portfolio_return.iloc[-1]
    )

    latest_date = (
        portfolio_return
        .index[-1]
        .date()
    )

    # Include a zero baseline before the trade when
    # measuring peak-to-trough deterioration.
    path_values = np.concatenate(
        [
            np.array([0.0]),
            portfolio_return.to_numpy(
                dtype=float
            ),
        ]
    )

    running_peak = np.maximum.accumulate(
        path_values
    )

    drawdown = (
        path_values
        - running_peak
    )

    max_drawdown_pct = float(
        drawdown.min()
        * 100.0
    )

    # -------------------------------------------------
    # Frozen-spread equilibrium crossing.
    # -------------------------------------------------

    log_a = np.log(
        future[fit.ticker_a]
    )

    log_b = np.log(
        future[fit.ticker_b]
    )

    spread = (
        log_a
        - fit.const
        - fit.beta * log_b
    )

    future_z = (
        spread
        - fit.spread_mean
    ) / fit.spread_std

    # Do not count the entry observation itself as a
    # completed mean-reversion event.
    after_entry_z = (
        future_z.iloc[1:]
    )

    if anomaly.z_score > 0:
        crossings = (
            after_entry_z[
                after_entry_z <= 0
            ]
        )
    else:
        crossings = (
            after_entry_z[
                after_entry_z >= 0
            ]
        )

    mean_reversion_date = None
    mean_reversion_return_pct = None

    if not crossings.empty:
        crossing_ts = (
            crossings.index[0]
        )

        mean_reversion_date = (
            crossing_ts.date()
        )

        mean_reversion_return_pct = (
            float(
                portfolio_return.loc[
                    crossing_ts
                ]
            )
            * 100.0
        )

    return PairForwardSimulation(
        simulation_id=(
            "SIM-"
            f"{signal.signal_id}"
        ),

        signal_id=signal.signal_id,

        as_of=signal.as_of,

        ticker_a=fit.ticker_a,
        ticker_b=fit.ticker_b,

        entry_date=(
            entry_date_ts.date()
        ),

        entry_metric=fit.metric,

        gross_capital=(
            gross_capital
        ),

        signal_z_score=(
            anomaly.z_score
        ),

        beta=fit.beta,

        strategy_direction=(
            strategy_direction
        ),

        weight_a=weight_a,
        weight_b=weight_b,

        notional_a=notional_a,
        notional_b=notional_b,

        forward_returns=tuple(
            forward_points
        ),

        latest_date=latest_date,

        return_to_latest_pct=(
            latest_value * 100.0
        ),

        pnl_to_latest=(
            latest_value
            * gross_capital
        ),

        max_drawdown_pct=(
            max_drawdown_pct
        ),

        mean_reversion_date=(
            mean_reversion_date
        ),

        mean_reversion_return_pct=(
            mean_reversion_return_pct
        ),

        transaction_cost_bps=(
            transaction_cost_bps
        ),
    )
