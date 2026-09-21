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
from datetime import date


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
        if as_of is not None and as_of > date.today():
            raise ValueError("The desk cannot travel to a date in the future.")

        with self._lock:
            changed = as_of != self._as_of
            self._as_of = as_of

        if changed:
            for listener in self._listeners:
                listener()


def as_clock(value: date | DeskClock | None) -> DeskClock:
    """Accept a fixed date wherever a clock is expected."""

    return value if isinstance(value, DeskClock) else DeskClock(value)
