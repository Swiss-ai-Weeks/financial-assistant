"""
Download historical news into the local archive.

    make news                         the book, current review window
    make news ARGS="--universe"       also the peer universe (pair partners)
    make news ARGS="--as-of 2026-02-27"

Providers: every one with a key in .env (Finnhub, EODHD,
Marketaux, GNews, NewsAPI, Alpha Vantage), then GDELT, which
needs none. The download can take as long as a rate limit
demands (GDELT: one request every five seconds) and can be
interrupted and resumed: finished slices are not requested
again. A provider whose daily quota runs out stops; the next
one still runs, and tomorrow's run continues where it stopped.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone

from financial_assistant.api.dependencies import (
    get_news_archive,
    get_news_downloaders,
    get_instrument_repository,
    get_portfolio_repository,
)
from financial_assistant.api.config import get_settings
from financial_assistant.api.repositories.gdelt import (
    GdeltRateLimited,
    GdeltRejected,
)
from financial_assistant.api.repositories.news_provider import (
    NewsProviderError,
)
from financial_assistant.api.services.news_service import NewsService


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])

    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=settings.as_of,
        help="last session of the review window (default: AS_OF, else today)",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="tickers to download (default: the book)",
    )
    parser.add_argument(
        "--universe",
        action="store_true",
        help="also download the peer universe",
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=None,
        help="download from this date instead of the review window's start (a year of history: --since 2025-09-22)",
    )
    parser.add_argument(
        "--providers",
        nargs="*",
        default=None,
        help="only these providers (e.g. finnhub), skipping slow ones such as gdelt",
    )

    args = parser.parse_args()

    instruments = get_instrument_repository()
    portfolio = get_portfolio_repository().load()

    names = {position.ticker: position.name for position in portfolio.positions}
    tickers = [t.upper() for t in args.tickers] if args.tickers else list(names)

    if args.universe:
        tickers += [t for t in instruments.universe if t not in tickers]

    # The same window the desk will ask for.
    start, end = NewsService(
        None,
        None,
        None,
        review_days=settings.review_days,
        as_of=args.as_of,
    ).window()

    if args.since is not None:
        start = datetime.combine(args.since, time.min, timezone.utc)

    archive = get_news_archive()

    for downloader in get_news_downloaders():
        if args.providers and downloader.name not in args.providers:
            continue

        print(
            f"{downloader.name}: {start:%Y-%m-%d} -> {end:%Y-%m-%d}, "
            f"{len(tickers)} tickers"
        )

        for ticker in tickers:
            company = names.get(ticker) or instruments.describe(ticker).name

            try:
                added = archive.download(
                    downloader,
                    ticker,
                    company,
                    start=start,
                    end=end,
                    on_progress=lambda line: print("  " + line, flush=True),
                )
            except (
                NewsProviderError,
                GdeltRateLimited,
                GdeltRejected,
                OSError,
                ValueError,
            ) as error:
                # Everything downloaded so far is kept. One
                # provider failing must not stop the next.
                print(f"  {ticker}: {error}")
                print(f"  {downloader.name} stopped; run again to resume.")
                break

            print(f"{ticker}: {added} new articles ({company})", flush=True)


if __name__ == "__main__":
    main()
