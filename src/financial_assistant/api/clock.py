"""
The date the desk believes it is.

Unset, the desk is live. Set, it is a replay: later prices and
later news do not exist for anything that asks the clock, which
is every repository that could leak the future.

It started as the AS_OF line in .env, read once at start-up.
Travelling in time then meant editing a file and restarting.
The clock keeps that value as its starting point and lets the
desk move it while running.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date, timedelta

# How far back the desk replays. The chart shows up to two
# years, but pair relationships need 504 sessions of history
# before the review window, so older dates would show a
# market with no relationships in it.
REPLAY_DAYS = 365


class DeskClock:
    def __init__(self, as_of: date | None = None):
        self._as_of = as_of
        self._lock = threading.Lock()
        self._listeners: list[Callable[[], None]] = []

    @property
    def as_of(self) -> date | None:
        with self._lock:
            return self._as_of

    def on_change(self, listener: Callable[[], None]) -> None:
        """
        Whatever memoises a result computed from the visible
        market must forget it when the visible market changes.
        """

        self._listeners.append(listener)

    def set(self, as_of: date | None) -> None:
        if as_of is not None:
            today = date.today()

            if as_of > today:
                raise ValueError("The desk cannot travel to a date in the future.")

            if as_of < today - timedelta(days=REPLAY_DAYS):
                raise ValueError(
                    f"The desk replays the last {REPLAY_DAYS} days only: "
                    f"{as_of.isoformat()} is too far back."
                )

            if as_of.weekday() >= 5:
                raise ValueError(f"{as_of.isoformat()} is not a trading session.")

        with self._lock:
            changed = as_of != self._as_of
            self._as_of = as_of

        if changed:
            for listener in self._listeners:
                listener()


def as_clock(value: date | DeskClock | None) -> DeskClock:
    """Accept a fixed date wherever a clock is expected."""

    return value if isinstance(value, DeskClock) else DeskClock(value)
