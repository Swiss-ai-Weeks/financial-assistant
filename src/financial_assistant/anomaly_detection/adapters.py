from __future__ import annotations

from datetime import (
    datetime,
    time,
    timezone,
)

from financial_assistant.domain import (
    AnomalyEvent,
)

from .models import PairAnomaly
from .signals import SignalAnomaly


def pair_anomaly_to_event(
    anomaly: PairAnomaly,
    *,
    observed_at: datetime | None = None,
) -> AnomalyEvent:
    """
    Convert a quantitative pair deviation into the
    neutral attention-event contract used by ClaimGraph.

    This adapter does NOT assert which company caused
    the divergence and does NOT interpret it as an
    investment signal.
    """

    # observed_at is the moment the deviation became
    # observable, e.g. the market close. Without it the
    # calendar date is carried at midnight UTC.
    detected_at = observed_at or datetime.combine(
        anomaly.monitoring_end,
        time.min,
        tzinfo=timezone.utc,
    )

    pair_label = (
        f"{anomaly.ticker_a}/"
        f"{anomaly.ticker_b}"
    )

    summary = (
        f"{pair_label} cointegration spread "
        f"deviation: z={anomaly.z_score:.2f} "
        f"versus threshold "
        f"{anomaly.threshold:.2f}"
    )

    return AnomalyEvent(
        anomaly_id=anomaly.anomaly_id,

        # ticker_a is only the primary routing entity.
        # ticker_b remains explicitly represented below.
        ticker=anomaly.ticker_a,

        related_entities=(
            anomaly.ticker_b,
        ),

        detected_at=detected_at,

        anomaly_type=(
            "cointegration_spread_deviation"
        ),

        summary=summary,

        metadata={
            "pair": pair_label,

            "ticker_a":
                anomaly.ticker_a,

            "ticker_b":
                anomaly.ticker_b,

            "z_score":
                anomaly.z_score,

            "max_abs_z":
                anomaly.max_abs_z,

            "threshold":
                anomaly.threshold,

            "n_days_flagged":
                anomaly.n_days_flagged,

            "relative_direction":
                anomaly.relative_direction,

            "beta":
                anomaly.beta,

            "const":
                anomaly.const,

            "formation_start":
                anomaly
                .formation_start
                .isoformat(),

            "formation_end":
                anomaly
                .formation_end
                .isoformat(),

            "monitoring_start":
                anomaly
                .monitoring_start
                .isoformat(),

            "monitoring_end":
                anomaly
                .monitoring_end
                .isoformat(),
        },
    )


def signal_anomaly_to_event(
    anomaly: SignalAnomaly,
    *,
    observed_at: datetime | None = None,
) -> AnomalyEvent:
    """
    Convert a single-instrument anomaly into the same
    neutral attention-event contract.

    Daily bars only become observable once the session
    has closed, so callers replaying history should
    pass the closing timestamp as observed_at.
    """

    detected_at = observed_at or datetime.combine(
        anomaly.observed_on,
        time.min,
        tzinfo=timezone.utc,
    )

    return AnomalyEvent(
        anomaly_id=anomaly.anomaly_id,
        ticker=anomaly.ticker,
        detected_at=detected_at,
        anomaly_type=anomaly.kind.value,
        summary=anomaly.summary,
        metadata={
            "strategy": anomaly.strategy.value,
            "z_score": anomaly.z_score,
            "threshold": anomaly.threshold,
            "direction": anomaly.direction,
            "observed_on": anomaly.observed_on.isoformat(),
            "detector_version": anomaly.detector_version,
            **anomaly.metrics,
        },
    )
