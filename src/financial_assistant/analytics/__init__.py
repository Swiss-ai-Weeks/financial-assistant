"""
Deterministic market analytics shared by the three stories.

    abnormal    what is unusual about a security, per horizon
    analogues   what happened next in comparable past situations

Everything here is point-in-time: a reading for day t uses
only information available at the close of day t.
"""

from .abnormal import (
    HORIZONS,
    HorizonReading,
    PeerReading,
    abnormal_return_series,
    read_horizon,
    read_peers,
)
from .analogues import (
    AnalogueOutcome,
    PairAnalogueBase,
    PairBreak,
    build_pair_analogue_base,
    single_name_analogues,
)

__all__ = [
    "HORIZONS",
    "HorizonReading",
    "PeerReading",
    "abnormal_return_series",
    "read_horizon",
    "read_peers",
    "AnalogueOutcome",
    "PairAnalogueBase",
    "PairBreak",
    "build_pair_analogue_base",
    "single_name_analogues",
]
