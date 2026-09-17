from __future__ import annotations

import argparse

import pandas as pd

from financial_assistant.anomaly_detection.historical import (
    scan_pairs_as_of,
)

from financial_assistant.simulation import (
    simulate_pair_forward,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prices",
        required=True,
    )

    parser.add_argument(
        "--formation-observations",
        type=int,
        default=252,
    )

    parser.add_argument(
        "--corr-min",
        type=float,
        default=0.70,
    )

    parser.add_argument(
        "--alpha",
        type=float,
        default=0.01,
    )

    parser.add_argument(
        "--entry",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--max-dates",
        type=int,
        default=120,
    )

    parser.add_argument(
        "--find-dates",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--future-observations",
        type=int,
        default=20,
    )

    args = parser.parse_args()

    prices = pd.read_csv(
        args.prices
    )

    prices["date"] = pd.to_datetime(
        prices["date"]
    )

    trading_dates = (
        prices["date"]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )

    minimum_index = (
        args.formation_observations
    )

    maximum_index = (
        len(trading_dates)
        - args.future_observations
        - 1
    )

    if maximum_index <= minimum_index:
        raise SystemExit(
            "Not enough history for both formation "
            "and future simulation windows."
        )

    eligible_dates = (
        trading_dates.iloc[
            minimum_index:
            maximum_index + 1
        ]
        .tail(args.max_dates)
        .iloc[::-1]
    )

    print(
        "PRICE DATES:",
        trading_dates.iloc[0].date(),
        "→",
        trading_dates.iloc[-1].date(),
    )

    print(
        "SEARCHING:",
        len(eligible_dates),
        "historical trading dates",
    )

    print(
        "FORMATION OBS:",
        args.formation_observations,
    )

    print(
        "CRITERIA:",
        f"corr >= {args.corr_min},",
        f"cointegration p < {args.alpha},",
        f"|z| > {args.entry}",
    )

    print()

    dates_found = 0

    for number, timestamp in enumerate(
        eligible_dates,
        start=1,
    ):
        as_of = timestamp.date()

        print(
            f"[{number:>3}/{len(eligible_dates)}] "
            f"{as_of}",
            end="",
            flush=True,
        )

        try:
            signals = scan_pairs_as_of(
                prices,
                as_of=as_of,
                formation_observations=(
                    args.formation_observations
                ),
                corr_min=args.corr_min,
                alpha=args.alpha,
                entry=args.entry,
            )

        except ValueError as exc:
            print(
                "  skipped:",
                exc,
            )
            continue

        if not signals:
            print("  no anomalies")
            continue

        print(
            f"  FOUND {len(signals)}"
        )

        dates_found += 1

        for rank, signal in enumerate(
            signals,
            start=1,
        ):
            fit = signal.fit
            anomaly = signal.anomaly

            print()
            print(
                f"  {rank}. "
                f"{fit.ticker_a}/"
                f"{fit.ticker_b}"
            )

            print(
                f"     z-score:     "
                f"{anomaly.z_score:+.3f}"
            )

            print(
                f"     correlation: "
                f"{fit.correlation:.3f}"
            )

            print(
                f"     coint p:     "
                f"{fit.pvalue:.5f}"
            )

            print(
                f"     beta:        "
                f"{fit.beta:.3f}"
            )

            print(
                f"     half-life:   "
                f"{fit.half_life_days}"
            )

            try:
                simulation = (
                    simulate_pair_forward(
                        signal,
                        prices,
                        gross_capital=10_000,
                        horizons=(
                            1,
                            5,
                            10,
                            20,
                        ),
                    )
                )

            except ValueError as exc:
                print(
                    "     simulation:  ",
                    exc,
                )
                continue

            print(
                f"     strategy:    "
                f"{simulation.strategy_direction}"
            )

            print(
                f"     entry:       "
                f"{simulation.entry_date}"
            )

            for point in (
                simulation.forward_returns
            ):
                print(
                    f"     "
                    f"{point.horizon_observations:>2}d: "
                    f"{point.return_pct:+7.2f}% "
                    f"${point.pnl:+8.2f}"
                )

            print(
                f"     latest:      "
                f"{simulation.return_to_latest_pct:+7.2f}%"
            )

            print(
                f"     drawdown:    "
                f"{simulation.max_drawdown_pct:+7.2f}%"
            )

            print(
                f"     reverted:    "
                f"{simulation.mean_reversion_date}"
            )

        print()
        print(
            "-" * 60
        )

        if (
            dates_found
            >= args.find_dates
        ):
            break

    print()
    print(
        "ANOMALY DATES FOUND:",
        dates_found,
    )


if __name__ == "__main__":
    main()
