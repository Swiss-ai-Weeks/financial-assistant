import numpy as np
import pandas as pd
import pytest

from financial_assistant.analytics import (
    abnormal_return_series,
    build_pair_analogue_base,
    read_horizon,
    read_peers,
    single_name_analogues,
)


# A one-year reading needs three years of history: one to
# estimate beta, one to measure volatility, one to judge.
SESSIONS = 820


def make_market(shock: float = 0.0, seed: int = 3) -> pd.DataFrame:
    """
    SPY plus three names driven by it. AAA and BBB share an
    extra sector factor; CCC does not. `shock` is added to
    AAA's final session only.
    """

    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end="2026-09-18", periods=SESSIONS)

    market = rng.normal(0.0003, 0.008, SESSIONS)
    sector = rng.normal(0, 0.006, SESSIONS)

    returns = {
        "SPY": market,
        "AAA": 1.2 * market + sector + rng.normal(0, 0.004, SESSIONS),
        "BBB": 1.1 * market + sector + rng.normal(0, 0.004, SESSIONS),
        "CCC": 0.8 * market + rng.normal(0, 0.010, SESSIONS),
    }

    returns["AAA"][-1] += shock

    # On the final session BBB does exactly what the market
    # implies, so whether it "followed" is not left to chance.
    returns["BBB"][-1] = 1.1 * market[-1]

    frames = []

    for ticker, series in returns.items():
        closes = 100 * np.exp(np.cumsum(series))
        volume = np.full(SESSIONS, 1_000_000.0)

        if ticker == "AAA" and shock:
            volume[-1] = 4_000_000

        frames.append(
            pd.DataFrame(
                {
                    "date": days,
                    "ticker": ticker,
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": volume,
                }
            )
        )

    return pd.concat(frames, ignore_index=True)


def test_a_shock_is_unusual_for_a_day_but_not_for_a_year():
    prices = make_market(shock=-0.09)

    day = read_horizon(prices, ticker="AAA", benchmark="SPY", horizon="1d")
    year = read_horizon(prices, ticker="AAA", benchmark="SPY", horizon="1y")

    assert day.unusual and day.z_score < -4
    assert day.abnormal_return_pct == pytest.approx(-9, abs=2.5)
    assert day.volume_unusual and day.volume_multiple == pytest.approx(4, rel=0.1)
    assert 0.9 < day.beta < 1.5

    # The same -9% is absorbed by a year of ordinary noise.
    assert not year.unusual


def test_market_moves_are_not_abnormal():
    """
    A name that only moved because the market did has a
    large return and an ordinary abnormal return.
    """

    prices = make_market()

    crash = prices["date"] == prices["date"].max()
    prices.loc[crash, "close"] *= np.where(
        prices.loc[crash, "ticker"] == "SPY", 0.95, 0.94
    )

    reading = read_horizon(prices, ticker="AAA", benchmark="SPY", horizon="1d")

    assert reading.return_pct < -4
    assert abs(reading.abnormal_return_pct) < abs(reading.return_pct) / 3


def test_reading_never_uses_later_sessions():
    """
    The z-score computed at a past date inside the full
    history must equal the one computed when that date was
    the latest session: thirty later sessions, including a
    9% shock, may not reach back.
    """

    from financial_assistant.analytics.abnormal import horizon_zscores, wide

    prices = make_market(shock=-0.09)
    cutoff = prices["date"].unique()[-30]

    at_the_time = read_horizon(
        prices[prices["date"] <= cutoff],
        ticker="AAA",
        benchmark="SPY",
        horizon="1w",
    )

    closes = wide(prices)
    abnormal, _ = abnormal_return_series(closes["AAA"], closes["SPY"])
    _, z = horizon_zscores(abnormal, 5)

    assert z.loc[cutoff] == pytest.approx(at_the_time.z_score)


def test_peers_are_ranked_by_past_co_movement_and_checked_for_following():
    prices = make_market(shock=-0.09)

    peers = read_peers(prices, ticker="AAA", benchmark="SPY", horizon="1d")

    # BBB shares AAA's sector factor; CCC does not qualify.
    assert [peer.ticker for peer in peers] == ["BBB"]
    assert peers[0].correlation > 0.5

    # The shock was AAA's alone.
    assert not peers[0].followed


def test_analogues_report_frequencies_with_their_sample_size():
    prices = make_market()

    outcome = single_name_analogues(
        prices,
        ticker="AAA",
        benchmark="SPY",
        sessions=1,
        z_score=-1.5,
        pool=("BBB", "CCC"),
    )

    assert outcome.analogues >= 20
    assert outcome.forward_sessions == 5

    total = (
        outcome.continuation_pct
        + outcome.reversion_pct
        + outcome.indeterminate_pct
    )

    assert total == pytest.approx(100)

    # Independent noise has no memory: neither outcome dominates.
    assert abs(outcome.continuation_pct - outcome.reversion_pct) < 25


def test_too_few_analogues_is_reported_as_unknown():
    assert (
        single_name_analogues(
            make_market(),
            ticker="AAA",
            benchmark="SPY",
            sessions=1,
            z_score=-14.0,
        )
        is None
    )


def test_pair_analogue_base_is_walk_forward():
    """
    Every recorded break must have been detected on a date
    whose outcome lies strictly after it.
    """

    rng = np.random.default_rng(5)
    days = pd.bdate_range(end="2026-09-18", periods=520)

    common = np.cumsum(rng.normal(0, 0.01, 520))
    frames = []

    for ticker, seed in (("AAA", 1), ("BBB", 2)):
        noise = np.random.default_rng(seed).normal(0, 0.004, 520)
        closes = 100 * np.exp(common + noise)

        if ticker == "AAA":
            closes[400:403] *= 0.93

        frames.append(
            pd.DataFrame(
                {
                    "date": days,
                    "ticker": ticker,
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": 1e6,
                }
            )
        )

    base = build_pair_analogue_base(
        pd.concat(frames, ignore_index=True),
        corr_min=0.5,
        step_sessions=1,
        lookback_sessions=200,
    )

    injected = [b for b in base.breaks if days[400].date() <= b.as_of <= days[403].date()]

    # One event, not one per day it stayed broken.
    assert len(injected) == 1

    event = injected[0]

    assert {event.ticker_a, event.ticker_b} == {"AAA", "BBB"}
    assert event.as_of == days[400].date()

    # AAA fell: below equilibrium if it is the dependent leg,
    # above it if BBB is.
    assert (event.z_score < -2) == (event.ticker_a == "AAA")
    assert abs(event.z_score) > 2

    # The dislocation was temporary, so the reversion trade paid.
    assert event.return_5_pct > 0
