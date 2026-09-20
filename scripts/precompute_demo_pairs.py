from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from financial_assistant.anomaly_detection.scalable import (
    fit_universe_pairs,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prices",
        default=(
            "data/cache/market/"
            "global_demo_daily.csv"
        ),
    )

    parser.add_argument(
        "--universe",
        default=(
            "data/universe/"
            "global_equities.csv"
        ),
    )

    parser.add_argument(
        "--as-of",
        default="2026-09-18",
    )

    parser.add_argument(
        "--formation-observations",
        type=int,
        default=252,
    )

    parser.add_argument(
        "--corr-floor",
        type=float,
        default=0.50,
    )

    parser.add_argument(
        "--alpha-ceiling",
        type=float,
        default=0.10,
    )

    parser.add_argument(
        "--max-peers",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--output",
        default=(
            "data/cache/market/"
            "demo_pair_fits.json"
        ),
    )

    args = parser.parse_args()

    prices = pd.read_csv(
        args.prices
    )

    prices["date"] = (
        pd.to_datetime(
            prices["date"]
        )
    )

    universe = pd.read_csv(
        args.universe
    )

    universe = universe.loc[
        universe[
            "mapping_status"
        ]
        == "mapped"
    ].copy()

    as_of = pd.Timestamp(
        args.as_of
    ).normalize()

    fits, summaries = fit_universe_pairs(
        prices, universe, as_of=as_of,
        formation_observations=args.formation_observations,
        corr_floor=args.corr_floor, alpha_ceiling=args.alpha_ceiling,
        max_peers_per_ticker=args.max_peers,
    )
    all_fits = []
    offset = 0
    for summary in summaries:
        for fit in fits[offset:offset + summary["fits"]]:
            all_fits.append({**fit.model_dump(mode="json"),
                             "universe_group": summary["group"]})
        offset += summary["fits"]

    payload = {
        "schema_version":
            "demo-pair-cache-v1",

        "as_of":
            as_of.date().isoformat(),

        "source_prices":
            args.prices,

        "formation_observations":
            args
            .formation_observations,

        "corr_floor":
            args.corr_floor,

        "alpha_ceiling":
            args.alpha_ceiling,

        "max_peers_per_ticker":
            args.max_peers,

        "groups":
            summaries,

        "fit_count":
            len(all_fits),

        "fits":
            all_fits,
    }

    output = Path(
        args.output
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "TOTAL FITS:",
        len(all_fits),
    )

    print(
        "WROTE:",
        output,
    )


if __name__ == "__main__":
    main()
