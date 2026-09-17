from datetime import date

import pandas as pd
import pytest

from financial_assistant.anomaly_detection.historical import (
    HistoricalPairSignal,
)

from financial_assistant.anomaly_detection.models import (
    PairAnomaly,
    PairFit,
)

from financial_assistant.simulation import (
    simulate_pair_forward,
)


AS_OF = date(
    2026,
    1,
    6,
)


def make_fit() -> PairFit:
    return PairFit(
        ticker_a="AAA",
        ticker_b="BBB",

        metric="close",

        formation_start=date(
            2025,
            1,
            1,
        ),

        formation_end=date(
            2026,
            1,
            5,
        ),

        correlation=0.90,

        const=0.0,
        beta=1.0,

        adf_stat=-4.5,
        pvalue=0.001,

        adf_lags=1,
        nobs=252,

        half_life_days=5.0,

        spread_mean=0.0,
        spread_std=0.1,
    )


def make_signal(
    *,
    z_score: float = 2.5,
) -> HistoricalPairSignal:
    fit = make_fit()

    anomaly = PairAnomaly(
        anomaly_id=(
            "PAIR-AAA-BBB-"
            "2026-01-06"
        ),

        ticker_a="AAA",
        ticker_b="BBB",

        metric="close",

        monitoring_start=AS_OF,
        monitoring_end=AS_OF,

        first_flag=AS_OF,

        threshold=2.0,
        n_days_flagged=1,

        z_score=z_score,
        max_abs_z=abs(z_score),

        relative_direction=(
            "a_above_equilibrium"
            if z_score > 0
            else "a_below_equilibrium"
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

    return HistoricalPairSignal(
        signal_id=(
            "HPS-AAA-BBB-"
            "2026-01-06"
        ),

        as_of=AS_OF,

        fit=fit,
        anomaly=anomaly,

        formation_observations=252,

        corr_min=0.70,
        alpha=0.01,
        entry=2.0,
    )


def make_future_prices() -> pd.DataFrame:
    """
    Signal is on Jan 6.

    Entry must therefore be Jan 7, not Jan 6.

    A starts at 110 on entry and falls toward B=100,
    benefiting a positive-z short-spread position.
    """

    observations = [
        (
            "2026-01-06",
            130.0,
            100.0,
        ),
        (
            "2026-01-07",
            110.0,
            100.0,
        ),
        (
            "2026-01-08",
            100.0,
            100.0,
        ),
        (
            "2026-01-09",
            99.0,
            100.0,
        ),
    ]

    rows = []

    for day, a, b in observations:
        rows.extend(
            [
                {
                    "date": day,
                    "ticker": "AAA",
                    "close": a,
                },
                {
                    "date": day,
                    "ticker": "BBB",
                    "close": b,
                },
            ]
        )

    return pd.DataFrame(rows)


def test_positive_z_shorts_spread():
    simulation = (
        simulate_pair_forward(
            make_signal(
                z_score=2.5
            ),
            make_future_prices(),
            gross_capital=10_000,
            horizons=(1,),
        )
    )

    assert (
        simulation.entry_date
        == date(
            2026,
            1,
            7,
        )
    )

    assert (
        simulation.strategy_direction
        == "short_spread"
    )

    assert simulation.weight_a == (
        pytest.approx(-0.5)
    )

    assert simulation.weight_b == (
        pytest.approx(0.5)
    )

    # AAA falls 110 -> 100.
    #
    # Short AAA has +9.0909% on its half of
    # gross capital. BBB is unchanged.
    #
    # Portfolio return:
    #   0.5 * 9.0909% = 4.54545%
    one_day = (
        simulation.forward_returns[0]
    )

    assert (
        one_day.horizon_observations
        == 1
    )

    assert one_day.return_pct == (
        pytest.approx(
            4.5454545
        )
    )

    assert one_day.pnl == (
        pytest.approx(
            454.54545
        )
    )


def test_negative_z_longs_spread():
    prices = (
        make_future_prices()
        .copy()
    )

    # Make A rise after entry, benefiting a
    # long-spread position.
    prices.loc[
        (
            prices["date"]
            == "2026-01-08"
        )
        & (
            prices["ticker"]
            == "AAA"
        ),
        "close",
    ] = 121.0

    simulation = (
        simulate_pair_forward(
            make_signal(
                z_score=-2.5
            ),
            prices,
            gross_capital=10_000,
            horizons=(1,),
        )
    )

    assert (
        simulation.strategy_direction
        == "long_spread"
    )

    assert simulation.weight_a == (
        pytest.approx(0.5)
    )

    assert simulation.weight_b == (
        pytest.approx(-0.5)
    )

    assert (
        simulation
        .forward_returns[0]
        .return_pct
        > 0
    )


def test_signal_date_is_never_used_as_entry():
    simulation = (
        simulate_pair_forward(
            make_signal(),
            make_future_prices(),
        )
    )

    assert (
        simulation.entry_date
        > simulation.as_of
    )


def test_detects_mean_reversion():
    simulation = (
        simulate_pair_forward(
            make_signal(),
            make_future_prices(),
        )
    )

    # Frozen equilibrium is A == B because:
    #
    # const = 0
    # beta = 1
    # spread_mean = 0
    #
    # This occurs on Jan 8.
    assert (
        simulation.mean_reversion_date
        == date(
            2026,
            1,
            8,
        )
    )

    assert (
        simulation
        .mean_reversion_return_pct
        == pytest.approx(
            4.5454545
        )
    )


def test_no_future_prices_is_rejected():
    prices = (
        make_future_prices()
    )

    prices = prices.loc[
        pd.to_datetime(
            prices["date"]
        ).dt.date
        <= AS_OF
    ]

    with pytest.raises(
        ValueError,
        match=(
            "No future common price "
            "observations"
        ),
    ):
        simulate_pair_forward(
            make_signal(),
            prices,
        )
