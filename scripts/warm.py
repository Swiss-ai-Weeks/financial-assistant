"""
Pre-build the slow caches so the first discovery of a demo is
instant: prices for the whole universe and the walk-forward
analogue record (minutes for ~140 names, then kept on disk).

Prints each stage as it starts, with elapsed time, so that
"slow" can be told apart from "stuck".
"""

from __future__ import annotations

import time

from financial_assistant.api.dependencies import get_discovery_service


def main() -> None:
    service = get_discovery_service()
    started = time.perf_counter()

    service.start()
    shown = None

    while True:
        job = service.job()

        if job.stage != shown and job.status == "running":
            shown = job.stage
            print(f"[{time.perf_counter() - started:6.0f}s] {shown}", flush=True)

        if job.status != "running":
            break

        time.sleep(1)

    elapsed = time.perf_counter() - started

    if job.status == "failed":
        raise SystemExit(f"[{elapsed:6.0f}s] FAILED: {job.error}")

    discovery = job.discovery

    print(
        f"[{elapsed:6.0f}s] Done: {discovery.analogue_breaks} historical breaks, "
        f"{len(discovery.setups)} new setups, "
        f"{len(discovery.on_your_desk)} already on the desk."
    )


if __name__ == "__main__":
    main()
