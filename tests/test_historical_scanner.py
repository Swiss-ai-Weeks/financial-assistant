from datetime import date

import pandas as pd
import pytest

from financial_assistant.anomaly_detection import (
    historical,
)

from financial_assistant.anomaly_detection.models import (
    PairAnomaly,
    PairFit,
)


AS_OF = date(
    2026,
    1,
    6,
)


def make_prices(
    *,
    include_future: bool,
) -> pd.DataFrame:
    dates = list(
        pd.date_range(
            "2026-01-01",
            "2026-01-06",
            freq="D",
        )
    )

    if include_future:
        dates.extend(
            pd.date_range(
                "2026-01-07",
                "2026-01-10",
                freq="D",
            )
        )

    rows = []

    for index, day in enumerate(
        dates
    ):
        rows.extend(
            [
                {
                    "date": day,
                    "ticker": "AAA",
                    "close": (
                        100.0 + index
                    ),
                },
                {
                    "date": day,
                    "ticker": "BBB",
                    "close": (
                        90.0 + index
                    ),
                },
            ]
        )

    return pd.DataFrame(
        rows
    )


def make_fit() -> PairFit:
    return PairFit(
        ticker_a="AAA",
        ticker_b="BBB",

        metric="close",

        formation_start=date(
            2026,
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

        adf_stat=-4.0,
        pvalue=0.001,

        adf_lags=1,
        nobs=5,

        half_life_days=4.0,

        spread_mean=0.0,
        spread_std=0.1,
    )


def make_anomaly() -> PairAnomaly:
    return PairAnomaly(
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

        z_score=2.5,
        max_abs_z=2.5,

        relative_direction=(
            "a_above_equilibrium"
        ),

        beta=1.0,
        const=0.0,

        formation_start=date(
            2026,
            1,
            1,
        ),

        formation_end=date(
            2026,
            1,
            5,
        ),
    )


def test_scanner_cannot_see_future_prices(
    monkeypatch,
):
    observed_max_dates = []

    def fake_fit_pairs(
        prices,
        *,
        start,
        end,
        metric,
        corr_min,
        alpha,
    ):
        observed_max_dates.append(
            pd.to_datetime(
                prices["date"]
            ).max().date()
        )

        assert end < AS_OF

        return (
            make_fit(),
        )

    def fake_monitor_pairs(
        prices,
        fits,
        *,
        start,
        end,
        entry,
    ):
        observed_max_dates.append(
            pd.to_datetime(
                prices["date"]
            ).max().date()
        )

        assert start == AS_OF
        assert end == AS_OF

        return (
            pd.DataFrame(),
            (
                make_anomaly(),
            ),
        )

    monkeypatch.setattr(
        historical,
        "fit_pairs",
        fake_fit_pairs,
    )

    monkeypatch.setattr(
        historical,
        "monitor_pairs",
        fake_monitor_pairs,
    )

    without_future = (
        historical.scan_pairs_as_of(
            make_prices(
                include_future=False
            ),
            as_of=AS_OF,
            formation_observations=5,
        )
    )

    with_future = (
        historical.scan_pairs_as_of(
            make_prices(
                include_future=True
            ),
            as_of=AS_OF,
            formation_observations=5,
        )
    )

    assert (
        without_future
        == with_future
    )

    assert observed_max_dates

    assert all(
        day <= AS_OF
        for day
        in observed_max_dates
    )


def test_formation_window_ends_before_as_of(
    monkeypatch,
):
    captured = {}

    def fake_fit_pairs(
        prices,
        *,
        start,
        end,
        metric,
        corr_min,
        alpha,
    ):
        captured["start"] = start
        captured["end"] = end

        return (
            make_fit(),
        )

    def fake_monitor_pairs(
        prices,
        fits,
        *,
        start,
        end,
        entry,
    ):
        captured[
            "monitor_start"
        ] = start

        captured[
            "monitor_end"
        ] = end

        return (
            pd.DataFrame(),
            (
                make_anomaly(),
            ),
        )

    monkeypatch.setattr(
        historical,
        "fit_pairs",
        fake_fit_pairs,
    )

    monkeypatch.setattr(
        historical,
        "monitor_pairs",
        fake_monitor_pairs,
    )

    historical.scan_pairs_as_of(
        make_prices(
            include_future=False
        ),
        as_of=AS_OF,
        formation_observations=5,
    )

    assert captured["start"] == date(
        2026,
        1,
        1,
    )

    assert captured["end"] == date(
        2026,
        1,
        5,
    )

    assert captured[
        "monitor_start"
    ] == AS_OF

    assert captured[
        "monitor_end"
    ] == AS_OF


def test_requires_enough_prior_history():
    with pytest.raises(
        ValueError,
        match=(
            "Insufficient formation "
            "history"
        ),
    ):
        historical.scan_pairs_as_of(
            make_prices(
                include_future=False
            ),
            as_of=AS_OF,
            formation_observations=20,
        )
