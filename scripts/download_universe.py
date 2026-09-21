"""
Fill the market cache for the whole investment universe.

    make universe                      every catalogued security
    make universe ARGS="--limit 500"   the first 500, to try it out

The desk never downloads a universe of thousands inside a
request: pair scans and discovery read what this script left
on disk, and only the book and the ticker on screen are
refreshed live. It is resumable. Fresh files are skipped, a
failed chunk is reported and the next run picks it up.
"""

from __future__ import annotations

import argparse
import time

from financial_assistant.api.dependencies import (
    get_instrument_repository,
    get_market_repository,
    get_portfolio_repository,
)
from financial_assistant.api.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--chunk", type=int, default=100)
    args = parser.parse_args()

    settings = get_settings()
    instruments = get_instrument_repository()
    market = get_market_repository()

    tickers = tuple(
        dict.fromkeys(
            (
                settings.benchmark,
                *get_portfolio_repository().load().tickers,
                *instruments.universe,
            )
        )
    )[: args.limit]

    started = time.perf_counter()

    print(
        f"{len(tickers)} securities "
        f"({instruments.catalog_size} in the catalogue), "
        f"{len(market.cached_tickers() & set(tickers))} already on disk"
    )

    available = market.download(
        tickers,
        chunk=args.chunk,
        on_progress=lambda line: print(
            f"[{time.perf_counter() - started:6.0f}s] {line}", flush=True
        ),
    )

    print(
        f"[{time.perf_counter() - started:6.0f}s] Done: "
        f"{available}/{len(tickers)} securities have history."
    )


if __name__ == "__main__":
    main()
