from datetime import date, timedelta

import pandas as pd
import pytest

from financial_assistant.anomaly_detection import (
    historical,
    scalable,
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
        formation_observations,
        corr_floor,
        alpha_ceiling,
        max_peers_per_ticker,
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
        scalable,
        "fit_bounded_pairs",
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
        formation_observations,
        corr_floor,
        alpha_ceiling,
        max_peers_per_ticker,
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
        scalable,
        "fit_bounded_pairs",
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

    assert captured["start"] == (AS_OF - timedelta(days=450))

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


def international_prices():
    import numpy as np
    rng = np.random.default_rng(0)
    dates = pd.bdate_range('2024-01-01', periods=290)
    common = 4 + np.cumsum(rng.normal(0, .012, len(dates)))
    noise = rng.normal(0, .002, len(dates))
    noise[270] = .07
    rows = []
    for i, day in enumerate(dates):
        for ticker, value in [('AAA', common[i] + noise[i]), ('BBB', common[i]),
                              ('CCC', common[i] + noise[i]), ('DDD', common[i])]:
            # Different exchanges have different holidays, including within
            # the same currency group. No column is globally complete.
            if i in ({15, 45} if ticker in ('AAA', 'BBB') else {25, 55}):
                continue
            rows.append(dict(date=day, ticker=ticker, close=np.exp(value)))
    universe = pd.DataFrame(dict(yahoo_ticker=['AAA', 'BBB', 'CCC', 'DDD'],
        universe=['Europe'] * 4, currency=['EUR'] * 4, mapping_status=['mapped'] * 4))
    return pd.DataFrame(rows), universe, dates[270].date()


def test_international_gaps_real_fits_and_future_invariance():
    prices, universe, day = international_prices()
    diagnostics = {}
    args = dict(as_of=day, universe=universe, corr_min=.65, alpha=.05, entry=1.5)
    first = historical.scan_pairs_as_of(prices, diagnostics=diagnostics, **args)
    assert first
    assert diagnostics['raw_fit_count'] >= diagnostics['eligible_fit_count'] > 0
    assert diagnostics['groups_processed'] == 1
    assert {t for s in first for t in (s.fit.ticker_a, s.fit.ticker_b)} == set(universe.yahoo_ticker)
    for signal in first:
        fit = signal.fit
        aligned = prices.pivot(index='date', columns='ticker', values='close')[[fit.ticker_a, fit.ticker_b]]
        assert len(aligned.loc[str(fit.formation_start):str(fit.formation_end)].dropna()) == 252
        assert fit.formation_end < day
    changed = prices.copy()
    changed.loc[changed.date.dt.date > day, 'close'] *= 999
    changed = pd.concat([changed, pd.DataFrame([dict(date=pd.Timestamp(day + timedelta(days=10)),
                                                   ticker='FUTURE', close=999)])])
    second_diagnostics = {}
    assert historical.scan_pairs_as_of(changed, diagnostics=second_diagnostics, **args) == first
    assert second_diagnostics == diagnostics


def test_groups_and_broad_policy_then_interactive_filters(monkeypatch):
    prices = make_prices(include_future=True)
    prices = pd.concat([prices.assign(ticker=t) for t in ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF', 'UNMAPPED']])
    universe = pd.DataFrame(dict(yahoo_ticker=['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF', 'UNMAPPED'],
        universe=['US', 'US', 'Europe', 'Europe', 'Europe', 'Europe', 'US'],
        currency=['USD', 'USD', 'USD', 'USD', None, None, 'USD'],
        mapping_status=['mapped'] * 6 + ['unmapped']))
    seen = []
    def fitter(frame, **kwargs):
        pair = tuple(sorted(frame.ticker.unique()))
        seen.append(pair)
        assert frame.date.max().date() < AS_OF
        assert kwargs['corr_floor'] == .51
        assert kwargs['alpha_ceiling'] == .09
        assert kwargs['max_peers_per_ticker'] == 3
        assert kwargs['formation_observations'] == 5
        return (make_fit().model_copy(update=dict(ticker_a=pair[0], ticker_b=pair[1],
                correlation=.64 if pair[0] == 'CCC' else .9,
                pvalue=.05 if pair[0] == 'EEE' else .001)),)
    monkeypatch.setattr(scalable, 'fit_bounded_pairs', fitter)
    def monitor(frame, fits, **kwargs):
        assert [(f.ticker_a, f.ticker_b) for f in fits] == [('AAA', 'BBB')]
        return pd.DataFrame(), (make_anomaly(),)
    monkeypatch.setattr(historical, 'monitor_pairs', monitor)
    diagnostics = {}
    historical.scan_pairs_as_of(prices, universe=universe, as_of=AS_OF,
        formation_observations=5, corr_floor=.51, alpha_ceiling=.09,
        max_peers_per_ticker=3, corr_min=.65, alpha=.05, diagnostics=diagnostics)
    assert set(seen) == {('AAA', 'BBB'), ('CCC', 'DDD'), ('EEE', 'FFF')}
    assert diagnostics['raw_fit_count'] == 3
    assert diagnostics['eligible_fit_count'] == 1
