"""
The desk on a chosen date sees nothing after it.

Every scan is run twice: once on the true history with the
clock set to D, once on a history that is identical up to D
and deliberately different afterwards. If anything downstream
of the clock looked ahead (a formation window, a correlation,
a yardstick, a rolling baseline), the two answers would differ.
"""

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from financial_assistant.api.clock import DeskClock
from financial_assistant.api.repositories import MarketDataRepository
from financial_assistant.api.repositories.market_data_repository import COLUMNS
from financial_assistant.api.services import anomaly_service
from financial_assistant.api.services.anomaly_service import AnomalyService


SESSIONS = 760
FORMATION = 504

DAYS = pd.bdate_range(end="2026-09-18", periods=SESSIONS)
AS_OF = DAYS[-60].date()
LATER = DAYS[-20].date()

BOOK = ("AAA", "CCC")
UNIVERSE = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "SPY")


def history(*, rewrite_after: date | None = None) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(11)

    def walk(scale=0.012):
        return np.cumsum(rng.normal(0, scale, SESSIONS))

    first, second = walk(), walk()

    closes = {
        "AAA": 4.0 + first,
        "BBB": 3.4 + 0.9 * first + rng.normal(0, 0.004, SESSIONS),
        "CCC": 4.3 + second,
        "DDD": 3.8 + 1.1 * second + rng.normal(0, 0.004, SESSIONS),
        "EEE": 4.0 + walk(),
        "FFF": 4.0 + walk(),
        "SPY": 6.0 + walk(0.006),
    }

    # The spread of AAA/BBB opens up shortly before AS_OF, so
    # there is a pair anomaly to find on that date.
    closes["AAA"] = closes["AAA"].copy()
    closes["AAA"][-70:] += 0.05

    volumes = {
        ticker: rng.lognormal(15, 0.25, SESSIONS) for ticker in closes
    }
    volumes["CCC"][-62] *= 9.0

    if rewrite_after is not None:
        other = np.random.default_rng(99)
        future = DAYS > pd.Timestamp(rewrite_after)

        for ticker in closes:
            closes[ticker] = closes[ticker].copy()
            closes[ticker][future] += np.cumsum(
                other.normal(0.01, 0.05, int(future.sum()))
            )
            volumes[ticker][future] *= other.lognormal(1.0, 1.0, int(future.sum()))

    frames = {}

    for ticker, log_close in closes.items():
        close = np.exp(log_close)

        frames[ticker] = pd.DataFrame(
            {
                "date": DAYS,
                "ticker": ticker,
                "open": close * 0.998,
                "high": close * 1.006,
                "low": close * 0.994,
                "close": close,
                "volume": volumes[ticker],
            }
        )[COLUMNS]

    return frames


def offline(*_, **__):
    raise AssertionError("a replay must never download")


def desk(tmp_path, frames, *, as_of=None, until: date | None = None):
    folder = tmp_path / f"market-{len(list(tmp_path.iterdir()))}"
    folder.mkdir()

    for ticker, frame in frames.items():
        if until is not None:
            frame = frame.loc[frame["date"] <= pd.Timestamp(until)]

        frame.to_csv(folder / f"{ticker}.csv", index=False)

    clock = DeskClock(as_of)

    market = MarketDataRepository(
        folder,
        history_days=1600,
        cache_minutes=10_000,
        as_of=clock,
        downloader=offline,
    )

    service = AnomalyService(
        SimpleNamespace(load=lambda: SimpleNamespace(tickers=BOOK)),
        market,
        SimpleNamespace(universe=UNIVERSE, sectors={}, groups={}),
        review_days=30,
        benchmark="SPY",
        formation_observations=FORMATION,
        corr_min=0.70,
        corr_min_same_sector=0.70,
        alpha=0.05,
        entry=2.0,
        recalibrate_every=21,
        recalibration_window=252,
    )

    return service, clock


def blotter(service) -> list[dict]:
    return [anomaly.model_dump(mode="json") for anomaly in service.list()]


@pytest.fixture(params=["exhaustive", "bounded"])
def path(request, monkeypatch):
    """Both fitters: the small-universe one and the batched one."""

    if request.param == "bounded":
        monkeypatch.setattr(anomaly_service, "LARGE_UNIVERSE", 3)

    return request.param


def test_the_future_cannot_change_what_the_desk_sees(tmp_path, path):
    true_history, _ = desk(tmp_path, history(), as_of=AS_OF)
    other_future, _ = desk(tmp_path, history(rewrite_after=AS_OF), as_of=AS_OF)
    no_future, _ = desk(tmp_path, history(), until=AS_OF)

    seen = blotter(true_history)

    assert {a["strategy"] for a in seen} >= {"pairs", "vwap"}

    assert seen == blotter(other_future)
    assert seen == blotter(no_future)

    scan = true_history.pair_scan(focus=BOOK)

    assert scan.model_dump() == other_future.pair_scan(focus=BOOK).model_dump()
    assert scan.model_dump() == no_future.pair_scan(focus=BOOK).model_dump()


def test_the_windows_are_ordered_and_end_on_the_chosen_date(tmp_path, path):
    service, _ = desk(tmp_path, history(), as_of=AS_OF)
    scan = service.pair_scan(focus=BOOK)

    assert scan.fits
    assert scan.monitoring_end == AS_OF
    assert scan.formation_end < scan.monitoring_start <= scan.monitoring_end

    for anomaly in service.list():
        assert anomaly.observed_on <= AS_OF

        if anomaly.strategy == "pairs":
            assert date.fromisoformat(anomaly.metrics["formation_end"]) < scan.monitoring_start


def test_the_formation_window_is_twenty_four_months_of_sessions(tmp_path, path):
    service, _ = desk(tmp_path, history(), as_of=AS_OF)
    scan = service.pair_scan(focus=BOOK)

    sessions = DAYS[(DAYS >= pd.Timestamp(scan.formation_start)) & (DAYS <= pd.Timestamp(scan.formation_end))]

    assert len(sessions) == FORMATION


def test_moving_the_clock_moves_every_scan(tmp_path, path):
    service, clock = desk(tmp_path, history(), as_of=AS_OF)
    clock.on_change(service.invalidate)

    earlier = service.pair_scan(focus=BOOK)

    clock.set(LATER)
    later = service.pair_scan(focus=BOOK)

    assert (earlier.monitoring_end, later.monitoring_end) == (AS_OF, LATER)
    assert later.formation_end > earlier.formation_end

    # And back: the same date is the same answer.
    clock.set(AS_OF)
    assert service.pair_scan(focus=BOOK).model_dump() == earlier.model_dump()


def test_the_spread_chart_is_the_scan(tmp_path, path):
    """The z on the chart is the z that raised the anomaly."""

    service, _ = desk(tmp_path, history(), as_of=AS_OF)

    flagged = [fit for fit in service.pair_scan(focus=BOOK).fits if fit.flagged]
    assert flagged

    for fit in flagged:
        spread = service.pair_spread(fit.ticker_a, fit.ticker_b)

        assert (spread.ticker_a, spread.ticker_b) == (fit.ticker_a, fit.ticker_b)
        assert spread.points[-1].time == AS_OF
        assert spread.points[-1].z_score == pytest.approx(fit.z_score, abs=1e-9)


def test_the_chart_is_the_scan_for_a_market_with_its_own_holidays(tmp_path, monkeypatch):
    monkeypatch.setattr(anomaly_service, "LARGE_UNIVERSE", 3)

    frames = history()

    for ticker in ("AAA", "BBB"):
        frame = frames[ticker]
        frames[ticker] = frame.loc[np.arange(len(frame)) % 40 != 5]

    service, _ = desk(tmp_path, frames, as_of=AS_OF)

    fit = next(f for f in service.pair_scan(focus=BOOK).fits if f.flagged)
    spread = service.pair_spread(fit.ticker_a, fit.ticker_b)

    assert spread.beta == pytest.approx(fit.beta, abs=1e-12)
    assert spread.points[-1].z_score == pytest.approx(fit.z_score, abs=1e-9)


def test_a_date_without_twenty_four_months_behind_it_fits_nothing(tmp_path, path):
    """Never a shorter window passed off as the 24-month one."""

    too_early = DAYS[FORMATION - 40].date()

    service, _ = desk(tmp_path, history(), as_of=too_early)

    assert service.pair_scan(focus=BOOK).fits == []

    # The single-instrument monitors need weeks, not years.
    assert all(a.strategy != "pairs" for a in service.list())
    assert all(a.observed_on <= too_early for a in service.list())


def test_a_scan_overtaken_by_time_travel_is_not_remembered(tmp_path):
    service, clock = desk(tmp_path, history(), as_of=AS_OF)
    clock.on_change(service.invalidate)

    market = service._market
    read = market.get_available
    travelled = []

    def read_then_travel(*args, **kwargs):
        prices = read(*args, **kwargs)

        if not travelled:
            travelled.append(True)
            clock.set(LATER)

        return prices

    market.get_available = read_then_travel

    # The first attempt read prices as of AS_OF and a calendar
    # as of LATER. The answer must be the clean one for LATER,
    # now and from the cache.
    clean, _ = desk(tmp_path, history(), as_of=LATER)
    expected = clean.pair_scan(focus=BOOK).model_dump()

    assert service.pair_scan(focus=BOOK).model_dump() == expected
    assert service.pair_scan(focus=BOOK).model_dump() == expected
