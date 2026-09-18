from datetime import date

import numpy as np
import pandas as pd
import pytest

from financial_assistant.anomaly_detection import (
    PairFit,
    monitor_pairs,
)


def make_prices(
    spread: float,
) -> pd.DataFrame:
    """
    Build a tiny deterministic monitoring series.

    B stays at 100.
    A = B * exp(spread)

    Therefore, for beta=1 and const=0:

        log(A) - log(B) = spread
    """

    dates = pd.date_range(
        "2026-09-01",
        periods=5,
        freq="D",
    )

    rows = []

    for day in dates:
        b = 100.0

        a = (
            b
            * np.exp(spread)
        )

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


def make_fit() -> PairFit:
    return PairFit(
        ticker_a="AAA",
        ticker_b="BBB",

        metric="close",

        formation_start=date(
            2020,
            9,
            13,
        ),

        formation_end=date(
            2025,
            9,
            13,
        ),

        correlation=0.90,

        const=0.0,
        beta=1.0,

        adf_stat=-4.5,
        pvalue=0.001,

        adf_lags=1,
        nobs=1000,

        half_life_days=8.0,

        spread_mean=0.0,
        spread_std=0.1,
    )


def test_monitor_flags_large_frozen_spread_deviation():
    prices = make_prices(
        spread=0.25
    )

    zscores, anomalies = (
        monitor_pairs(
            prices,
            (make_fit(),),
            start="2026-09-01",
            end="2026-09-05",
            entry=2.0,
        )
    )

    assert len(anomalies) == 1

    anomaly = anomalies[0]

    assert anomaly.ticker_a == "AAA"
    assert anomaly.ticker_b == "BBB"

    assert anomaly.z_score == (
        pytest.approx(2.5)
    )

    assert (
        anomaly.relative_direction
        == "a_above_equilibrium"
    )

    assert anomaly.n_days_flagged == 5

    assert "AAA/BBB" in zscores.columns


def test_monitor_does_not_flag_small_deviation():
    prices = make_prices(
        spread=0.10
    )

    _, anomalies = monitor_pairs(
        prices,
        (make_fit(),),
        start="2026-09-01",
        end="2026-09-05",
        entry=2.0,
    )

    assert anomalies == ()


def test_monitor_uses_frozen_fit_parameters():
    """
    Changing the frozen spread mean changes the
    monitored z-score without any model re-fitting.
    """

    prices = make_prices(
        spread=0.25
    )

    original = make_fit()

    shifted = original.model_copy(
        update={
            "spread_mean": 0.20,
        }
    )

    _, original_anomalies = (
        monitor_pairs(
            prices,
            (original,),
            start="2026-09-01",
            end="2026-09-05",
            entry=2.0,
        )
    )

    _, shifted_anomalies = (
        monitor_pairs(
            prices,
            (shifted,),
            start="2026-09-01",
            end="2026-09-05",
            entry=2.0,
        )
    )

    assert len(
        original_anomalies
    ) == 1

    assert shifted_anomalies == ()

