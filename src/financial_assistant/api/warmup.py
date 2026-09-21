"""
What the first visitor would otherwise wait for, done when the
desk starts.

Nothing here is new work: it calls the same services the first
paint of the desk calls, in the order that paint needs them, so
their caches are full before anyone opens the page. It runs in
a background thread. The API answers from the first second; a
request that arrives mid-warm-up simply waits on the same
computation instead of starting its own.

Every step is allowed to fail. A desk without network, or with
an empty price cache, must still start.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable


log = logging.getLogger("uvicorn.error")

_state = {"stage": "idle", "done": False, "seconds": None}


def status() -> dict:
    return dict(_state)


def _steps() -> list[tuple[str, Callable[[], object]]]:
    from financial_assistant.api import dependencies as deps
    from financial_assistant.api.services.anomaly_service import LARGE_UNIVERSE

    settings = deps.get_settings()
    book = deps.get_portfolio_repository().load().tickers
    universe = deps.get_instrument_repository().universe

    def load_universe():
        # Reading thousands of CSVs is seconds of disk the first
        # pair scan would pay. Only the book may be downloaded.
        return deps.get_market_repository().get_available(
            tuple(dict.fromkeys((settings.benchmark, *book, *universe))),
            refresh=(
                None
                if len(universe) <= LARGE_UNIVERSE
                else (settings.benchmark, *book)
            ),
        )

    return [
        ("prices of the universe", load_universe),
        ("book and tape", lambda: deps.get_portfolio_service().view()),
        ("anomalies on the book", lambda: deps.get_anomaly_service().list()),
        ("post-mortem", lambda: deps.get_postmortem_service().review()),
        ("news on the book", lambda: deps.get_news_service().portfolio_feed()),
        ("models", lambda: deps.get_investigation_service().models()),
    ]


def run() -> None:
    started = time.perf_counter()

    try:
        steps = _steps()
    except Exception as error:
        log.warning("warm-up skipped: %s", error)
        _state.update(stage="skipped", done=True)

        return

    for label, step in steps:
        _state["stage"] = label
        began = time.perf_counter()

        try:
            step()
            log.info("warm-up: %s (%.1fs)", label, time.perf_counter() - began)
        except Exception as error:
            log.warning("warm-up: %s failed: %s", label, error)

    _state.update(
        stage="ready",
        done=True,
        seconds=round(time.perf_counter() - started, 1),
    )

    log.info("warm-up finished in %.1fs", _state["seconds"])


def start_in_background() -> threading.Thread:
    thread = threading.Thread(target=run, name="warm-up", daemon=True)
    thread.start()

    return thread
