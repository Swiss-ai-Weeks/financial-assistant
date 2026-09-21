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
import os
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

    def refresh_universe():
        # Requests never download the universe, so without this
        # its prices would stay at the day `make universe` last
        # ran while the book moved on. Fresh files are skipped,
        # which makes a restart cheap; the network calls do not
        # hold the price lock, so the desk stays responsive.
        if os.environ.get("UNIVERSE_REFRESH_ON_START", "1") == "0":
            return None

        if len(universe) <= LARGE_UNIVERSE:
            return None

        market = deps.get_market_repository()

        market.download(
            tuple(dict.fromkeys((settings.benchmark, *book, *universe))),
            on_progress=lambda line: log.info("universe prices: %s", line),
        )

        # What was scanned before the refresh saw older prices.
        deps.get_anomaly_service().invalidate()

    return [
        ("prices of the universe", load_universe),
        ("book and tape", lambda: deps.get_portfolio_service().view()),
        ("anomalies on the book", lambda: deps.get_anomaly_service().list()),
        ("post-mortem", lambda: deps.get_postmortem_service().review()),
        ("news on the book", lambda: deps.get_news_service().portfolio_feed()),
        ("models", lambda: deps.get_investigation_service().models()),
        # Last, and long: everything above is already usable.
        ("refresh of stale universe prices", refresh_universe),
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
