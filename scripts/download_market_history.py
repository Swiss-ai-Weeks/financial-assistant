from __future__ import annotations

import argparse
from pathlib import Path

from financial_assistant.market_data import (
    download_daily_prices,
)


def read_tickers(
    path: Path,
) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in path.read_text().splitlines()
        if (
            line.strip()
            and not line
            .strip()
            .startswith("#")
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--tickers-file",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--start",
        required=True,
    )

    parser.add_argument(
        "--end",
        required=True,
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    tickers = read_tickers(
        args.tickers_file
    )

    prices, manifest = (
        download_daily_prices(
            tickers,
            start=args.start,
            end=args.end,
        )
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    prices.to_csv(
        args.output,
        index=False,
    )

    manifest_path = (
        args.output.with_suffix(
            ".manifest.json"
        )
    )

    manifest_path.write_text(
        manifest.model_dump_json(
            indent=2
        )
        + "\n"
    )

    print(
        "TICKERS:",
        len(tickers),
    )

    print(
        "ROWS:",
        len(prices),
    )

    print(
        "DATES:",
        (
            prices["date"].min()
            if not prices.empty
            else None
        ),
        "→",
        (
            prices["date"].max()
            if not prices.empty
            else None
        ),
    )

    print(
        "WROTE:",
        args.output,
    )

    print(
        "WROTE:",
        manifest_path,
    )


if __name__ == "__main__":
    main()
