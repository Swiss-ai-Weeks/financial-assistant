from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from financial_assistant.anomaly_detection import (
    SignalKind,
    StrategyKind,
    detect_signal_anomalies,
    detect_trend_breaks,
    detect_twap_deviations,
    detect_volume_spikes,
    detect_vwap_deviations,
    signal_anomaly_to_event,
)


def make_prices(closes, volumes=None) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    days = pd.bdate_range("2025-01-01", periods=len(closes))

    return pd.DataFrame(
        {
            "date": days,
            "ticker": "AAA",
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": (
                np.full(len(closes), 1_000_000.0)
                if volumes is None
                else np.asarray(volumes, dtype=float)
            ),
        }
    )


def quiet_closes(n: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)

    return 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))


def test_volume_spike_is_flagged_on_the_spike_day_only():
    rng = np.random.default_rng(1)
    volumes = rng.normal(1_000_000, 50_000, 120)
    volumes[100] = 4_000_000

    prices = make_prices(quiet_closes(120), volumes)
    anomalies = detect_volume_spikes(prices, ticker="AAA")

    assert [a.observed_on for a in anomalies] == [
        prices["date"].iloc[100].date()
    ]

    spike = anomalies[0]

    assert spike.kind == SignalKind.VOLUME_SPIKE
    assert spike.strategy == StrategyKind.VWAP
    assert spike.metrics["volume_multiple"] > 3.5


def test_detectors_never_look_ahead():
    """
    Appending future sessions must not change what was
    detected in the past.
    """

    closes = quiet_closes(160)
    closes[120:] *= 0.93

    volumes = np.full(160, 1_000_000.0)
    volumes[120] = 5_000_000

    full = make_prices(closes, volumes)
    truncated = full.iloc[:130]
    cutoff = truncated["date"].max()

    def ids(frame):
        return {
            a.anomaly_id
            for a in detect_signal_anomalies(frame, ticker="AAA", end=cutoff)
        }

    assert ids(truncated)
    assert ids(truncated) == ids(full)


def test_vwap_deviation_sign_matches_the_move():
    closes = quiet_closes(140)
    closes[130] *= 0.92

    prices = make_prices(closes)
    drop_day = prices["date"].iloc[130].date()

    anomalies = detect_vwap_deviations(prices, ticker="AAA")
    drop = next(a for a in anomalies if a.observed_on == drop_day)

    assert drop.z_score < 0
    assert drop.direction == "below"
    assert drop.metrics["deviation_pct"] < 0


def test_twap_detector_measures_drift_against_arrival_price():
    closes = quiet_closes(140)
    closes[130:] *= np.linspace(1.02, 1.10, 10)

    prices = make_prices(closes)

    anomalies = detect_twap_deviations(
        prices,
        ticker="AAA",
        start=prices["date"].iloc[130],
    )

    assert anomalies
    assert all(a.strategy == StrategyKind.TWAP for a in anomalies)
    assert all(a.direction == "above" for a in anomalies)
    assert all(a.metrics["shortfall_pct"] > 0 for a in anomalies)


def test_trend_detector_separates_crosses_from_whipsaws():
    closes = np.concatenate(
        [
            np.linspace(100, 80, 60),   # downtrend: fast below slow
            np.linspace(80, 110, 40),   # reversal: golden cross
            np.linspace(110, 111, 10),
        ]
    )

    # A violent one-day round trip forces a cross that
    # reverses within a few sessions.
    closes = np.concatenate([closes, [80, 78, 125, 128, 130]])

    anomalies = detect_trend_breaks(make_prices(closes), ticker="AAA")
    kinds = [a.kind for a in sorted(anomalies, key=lambda a: a.observed_on)]

    assert kinds[0] == SignalKind.TREND_CROSS
    assert anomalies[0].strategy == StrategyKind.TREND
    assert SignalKind.TREND_WHIPSAW in kinds

    whipsaw = next(a for a in anomalies if a.kind == SignalKind.TREND_WHIPSAW)

    assert whipsaw.metrics["sessions_since_previous_cross"] <= 5


def test_trend_detector_rejects_inverted_windows():
    with pytest.raises(ValueError):
        detect_trend_breaks(
            make_prices(quiet_closes(60)),
            ticker="AAA",
            fast=25,
            slow=7,
        )


def test_signal_anomaly_becomes_a_neutral_attention_event():
    volumes = np.full(80, 1_000_000.0) + np.arange(80) * 10.0
    volumes[70] = 6_000_000

    anomaly = detect_volume_spikes(
        make_prices(quiet_closes(80), volumes), ticker="AAA"
    )[0]

    observed_at = datetime(2025, 4, 9, 21, tzinfo=timezone.utc)
    event = signal_anomaly_to_event(anomaly, observed_at=observed_at)

    assert event.anomaly_id == anomaly.anomaly_id
    assert event.ticker == "AAA"
    assert event.anomaly_type == "volume_spike"
    assert event.detected_at == observed_at
    assert event.metadata["strategy"] == "vwap"
    assert event.related_entities == ()
