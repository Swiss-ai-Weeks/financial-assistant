from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from financial_assistant.anomaly_detection.historical import scan_pairs_as_of
from financial_assistant.simulation import simulate_pair_forward

from .abnormal import abnormal_return_series, horizon_zscores, wide


FORWARD_SESSIONS = 5
Z_TOLERANCE = 0.75

# A forward move smaller than this fraction of a typical
# forward move is called neither continuation nor reversal.
INDETERMINATE_BAND = 0.5


class AnalogueOutcome(BaseModel):
    """
    What happened after comparable past situations.

    These are historical frequencies, not a forecast: they
    say how often something followed, not that it will.
    """

    model_config = ConfigDict(frozen=True)

    scope: str
    forward_sessions: int

    analogues: int
    continuation_pct: float
    reversion_pct: float
    indeterminate_pct: float

    # Mean forward abnormal return, signed in the direction
    # of the original move (positive = it kept going).
    expected_abnormal_return_pct: float


def _classify(forward: np.ndarray, typical: float) -> tuple[float, float, float]:
    band = INDETERMINATE_BAND * typical

    continued = float((forward > band).mean()) * 100
    reverted = float((forward < -band).mean()) * 100

    return continued, reverted, 100.0 - continued - reverted


def single_name_analogues(
    prices: pd.DataFrame,
    *,
    ticker: str,
    benchmark: str,
    sessions: int,
    z_score: float,
    pool: tuple[str, ...] = (),
) -> AnalogueOutcome | None:
    """
    Past days on which a security stood as far from normal,
    in the same direction, over the same horizon; and what
    its abnormal return did over the following sessions.

    One name rarely has enough history on its own, so
    analogues are pooled across `pool`. Events are taken at
    least one horizon apart so overlapping windows are not
    counted as separate evidence, and only events whose
    forward window has fully elapsed are used.
    """

    closes = wide(prices)
    market = closes[benchmark]
    direction = np.sign(z_score)

    if direction == 0:
        return None

    forward_moves: list[float] = []
    typical_moves: list[float] = []

    for name in dict.fromkeys((ticker, *pool)):
        if name not in closes or name == benchmark:
            continue

        abnormal, _ = abnormal_return_series(closes[name].dropna(), market)
        _, z = horizon_zscores(abnormal, sessions)

        forward = (
            abnormal.rolling(FORWARD_SESSIONS).sum().shift(-FORWARD_SESSIONS)
        )

        typical_moves.append(float(forward.std()))

        # The latest FORWARD_SESSIONS have no outcome yet and
        # drop out here, together with today's own reading.
        eligible = z[(z - z_score).abs() <= Z_TOLERANCE].index
        eligible = [day for day in eligible if pd.notna(forward.loc[day])]

        last_kept = None
        positions = {day: i for i, day in enumerate(abnormal.index)}

        for day in eligible:
            if (
                last_kept is not None
                and positions[day] - positions[last_kept]
                < max(sessions, FORWARD_SESSIONS)
            ):
                continue

            last_kept = day
            forward_moves.append(float(forward.loc[day] * direction))

    if len(forward_moves) < 5:
        return None

    moves = np.asarray(forward_moves)
    continued, reverted, unclear = _classify(moves, float(np.nanmean(typical_moves)))

    return AnalogueOutcome(
        scope=(
            f"{ticker} and {len(pool)} comparable securities"
            if pool
            else ticker
        ),
        forward_sessions=FORWARD_SESSIONS,
        analogues=len(moves),
        continuation_pct=continued,
        reversion_pct=reverted,
        indeterminate_pct=unclear,
        expected_abnormal_return_pct=float(np.expm1(moves.mean())) * 100,
    )


# -----------------------------------------------------
# Relationship breaks
# -----------------------------------------------------


class PairBreak(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    ticker_a: str
    ticker_b: str
    z_score: float

    # Return of the mechanical mean-reversion trade entered
    # at the next open, in percent of gross capital.
    return_5_pct: float | None
    return_10_pct: float | None
    reverted: bool


class PairAnalogueBase(BaseModel):
    """
    Out-of-sample record of what happened after cointegrated
    pairs broke.

    Walk-forward: at each past date the relationships are
    fitted ONLY on the year before it, the break is observed
    on that date, and the outcome is measured afterwards.
    Nothing in a break's own future took part in finding it.
    """

    model_config = ConfigDict(frozen=True)

    universe_size: int
    first_as_of: date | None
    last_as_of: date | None
    breaks: tuple[PairBreak, ...]

    def outcome(self, z_score: float) -> AnalogueOutcome | None:
        comparable = [
            item
            for item in self.breaks
            if item.return_10_pct is not None
            and abs(abs(item.z_score) - abs(z_score)) <= 1.0
        ]

        if len(comparable) < 5:
            return None

        returns = np.asarray([item.return_10_pct for item in comparable])

        # For a relationship break the natural question is
        # reversed: the "move" is the divergence, so a
        # profitable reversion trade means it did NOT go on.
        reverted = float((returns > 0.5).mean()) * 100
        continued = float((returns < -0.5).mean()) * 100

        return AnalogueOutcome(
            scope=f"out-of-sample pair breaks, {self.universe_size} securities",
            forward_sessions=10,
            analogues=len(comparable),
            continuation_pct=continued,
            reversion_pct=reverted,
            indeterminate_pct=100.0 - continued - reverted,
            expected_abnormal_return_pct=float(returns.mean()),
        )


def build_pair_analogue_base(
    prices: pd.DataFrame,
    *,
    formation_observations: int = 252,
    corr_min: float = 0.70,
    alpha: float = 0.05,
    entry: float = 2.0,
    sectors: dict[str, str] | None = None,
    corr_min_same_sector: float | None = None,
    step_sessions: int = 10,
    lookback_sessions: int = 500,
    until: date | None = None,
    bounded: bool = False,
) -> PairAnalogueBase:
    """
    Scan history every `step_sessions` and record each new
    break together with its outcome.

    A pair that stays broken across consecutive scans is one
    event, recorded when it first appears.
    """

    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()

    sessions = sorted(frame["date"].unique())

    if until is not None:
        sessions = [day for day in sessions if day.date() <= until]

    # The latest sessions are left out: their outcome has not
    # happened yet.
    usable = sessions[formation_observations:-10]
    scan_days = usable[-lookback_sessions::step_sessions]

    breaks: list[PairBreak] = []
    previously_broken: set[tuple[str, ...]] = set()

    for day in scan_days:
        try:
            signals = scan_pairs_as_of(
                frame,
                as_of=day.date(),
                formation_observations=formation_observations,
                corr_min=corr_min,
                alpha=alpha,
                entry=entry,
                sectors=sectors,
                corr_min_same_sector=corr_min_same_sector,
                bounded=bounded,
            )
        except ValueError:
            continue

        broken_now = set()

        for signal in signals:
            pair = (signal.fit.ticker_a, signal.fit.ticker_b)

            # Which leg is the dependent one can change from
            # one scan to the next. It is still the same pair,
            # and a break that persists is still one event.
            identity = tuple(sorted(pair))
            broken_now.add(identity)

            if identity in previously_broken:
                continue

            try:
                simulation = simulate_pair_forward(
                    signal, frame, horizons=(5, 10)
                )
            except ValueError:
                continue

            outcomes = {
                point.horizon_observations: point.return_pct
                for point in simulation.forward_returns
            }

            breaks.append(
                PairBreak(
                    as_of=signal.as_of,
                    ticker_a=pair[0],
                    ticker_b=pair[1],
                    z_score=signal.anomaly.z_score,
                    return_5_pct=outcomes.get(5),
                    return_10_pct=outcomes.get(10),
                    reverted=simulation.mean_reversion_date is not None,
                )
            )

        previously_broken = broken_now

    return PairAnalogueBase(
        universe_size=int(frame["ticker"].nunique()),
        first_as_of=scan_days[0].date() if scan_days else None,
        last_as_of=scan_days[-1].date() if scan_days else None,
        breaks=tuple(breaks),
    )
