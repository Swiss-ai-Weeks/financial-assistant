from __future__ import annotations

import json
import time

from investigation_api import investigate, public_models

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)

from pathlib import Path

import pandas as pd

from financial_assistant.anomaly_detection.cointegration import (
    monitor_pairs,
)

from financial_assistant.anomaly_detection.models import (
    PairFit,
)


HOST = "127.0.0.1"
PORT = 8001

PRICE_PATH = Path(
    "data/cache/market/global_demo_daily.csv"
)

FIT_PATH = Path(
    "data/cache/market/demo_pair_fits.json"
)


# ---------------------------------------------------------
# Load expensive invariant data ONCE when the API starts.
# ---------------------------------------------------------

print("Loading market cache...")

PRICES = pd.read_csv(
    PRICE_PATH
)

PRICES["date"] = pd.to_datetime(
    PRICES["date"]
)


print("Loading pair-fit cache...")

FIT_PAYLOAD = json.loads(
    FIT_PATH.read_text(
        encoding="utf-8"
    )
)


FIT_RECORDS = tuple(
    FIT_PAYLOAD["fits"]
)


ALL_FITS = tuple(
    PairFit.model_validate(
        {
            key: value
            for key, value
            in record.items()
            if key in PairFit.model_fields
        }
    )
    for record in FIT_RECORDS
)


UNIVERSE_GROUP_BY_PAIR = {
    (
        record["ticker_a"],
        record["ticker_b"],
    ): record.get(
        "universe_group",
        "unknown",
    )
    for record in FIT_RECORDS
}

AS_OF = pd.Timestamp(
    FIT_PAYLOAD["as_of"]
).date()

CORR_FLOOR = float(
    FIT_PAYLOAD["corr_floor"]
)

ALPHA_CEILING = float(
    FIT_PAYLOAD["alpha_ceiling"]
)


def scan(
    *,
    corr_min: float,
    alpha: float,
    entry: float,
) -> dict:
    """
    Apply human-selected anomaly criteria to the
    precomputed statistical relationships.

    Pair fitting is invariant for this as-of date.

    Changing corr/p/z therefore genuinely changes
    which relationships satisfy the user's criteria
    without pointlessly repeating the same regression.
    """

    if not CORR_FLOOR <= corr_min <= 1.0:
        raise ValueError(
            f"corr_min must be between "
            f"{CORR_FLOOR} and 1.0"
        )

    if not 0.0001 <= alpha <= ALPHA_CEILING:
        raise ValueError(
            f"alpha must be between "
            f"0.0001 and {ALPHA_CEILING}"
        )

    if not 0.5 <= entry <= 4.0:
        raise ValueError(
            "entry must be between 0.5 and 4.0"
        )


    started = time.perf_counter()


    # -----------------------------------------------------
    # Human-controlled relationship criteria.
    # -----------------------------------------------------

    eligible_fits = tuple(
        fit
        for fit in ALL_FITS
        if (
            fit.correlation >= corr_min
            and fit.pvalue < alpha
        )
    )


    # -----------------------------------------------------
    # Recalculate the anomaly state using the selected
    # z-score threshold on the latest observation.
    # -----------------------------------------------------

    _, anomalies = monitor_pairs(
        PRICES,
        eligible_fits,
        start=AS_OF,
        end=AS_OF,
        entry=entry,
    )


    fit_by_pair = {
        (
            fit.ticker_a,
            fit.ticker_b,
        ): fit
        for fit in eligible_fits
    }


    candidates = []

    for anomaly in anomalies:
        pair = (
            anomaly.ticker_a,
            anomaly.ticker_b,
        )

        fit = fit_by_pair[pair]

        candidates.append(
            {
                "pair": (
                    f"{fit.ticker_a}/"
                    f"{fit.ticker_b}"
                ),

                "universe_group":
                    UNIVERSE_GROUP_BY_PAIR.get(
                        pair,
                        "unknown",
                    ),

                "ticker_a":
                    fit.ticker_a,

                "ticker_b":
                    fit.ticker_b,

                "signal_date":
                    AS_OF.isoformat(),

                "z_score":
                    anomaly.z_score,

                "threshold":
                    anomaly.threshold,

                "correlation":
                    fit.correlation,

                "cointegration_p":
                    fit.pvalue,

                "beta":
                    fit.beta,

                "half_life_days":
                    fit.half_life_days,

                "relative_direction":
                    anomaly.relative_direction,

                "formation_start":
                    fit.formation_start.isoformat(),

                "formation_end":
                    fit.formation_end.isoformat(),
            }
        )


    candidates.sort(
        key=lambda item: (
            -abs(
                item["z_score"]
            ),
            item["pair"],
        )
    )


    elapsed_ms = (
        time.perf_counter()
        - started
    ) * 1000


    return {
        "as_of":
            AS_OF.isoformat(),

        "criteria": {
            "corr_min":
                corr_min,

            "alpha":
                alpha,

            "entry":
                entry,
        },

        "cache": {
            "price_securities":
                int(
                    PRICES[
                        "ticker"
                    ].nunique()
                ),

            "pair_fits":
                len(ALL_FITS),

            "corr_floor":
                CORR_FLOOR,

            "alpha_ceiling":
                ALPHA_CEILING,

            "max_peers_per_ticker":
                FIT_PAYLOAD[
                    "max_peers_per_ticker"
                ],

            "formation_observations":
                FIT_PAYLOAD[
                    "formation_observations"
                ],
        },

        "eligible_fit_count":
            len(eligible_fits),

        "candidate_count":
            len(candidates),

        # Keep the browser payload manageable.
        "candidates":
            candidates[:50],

        "elapsed_ms":
            round(
                elapsed_ms,
                1,
            ),
    }


class Handler(
    BaseHTTPRequestHandler
):
    def send_json(
        self,
        status: int,
        payload: dict,
    ) -> None:
        body = json.dumps(
            payload
        ).encode("utf-8")

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            "application/json",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.end_headers()

        self.wfile.write(
            body
        )


    def do_GET(self) -> None:
        if self.path == "/api/investigations/models":
            self.send_json(200, public_models())
            return
        if self.path == "/api/health":
            self.send_json(
                200,
                {
                    "status": "ok",

                    "as_of":
                        AS_OF.isoformat(),

                    "securities":
                        int(
                            PRICES[
                                "ticker"
                            ].nunique()
                        ),

                    "pair_fits":
                        len(ALL_FITS),
                },
            )

            return

        self.send_json(
            404,
            {
                "error":
                    "not found"
            },
        )


    def do_POST(self) -> None:
        if (
            self.path
            not in ("/api/anomalies/scan", "/api/investigations")
        ):
            self.send_json(
                404,
                {
                    "error":
                        "not found"
                },
            )

            return

        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            raw = self.rfile.read(
                length
            )

            request = (
                json.loads(raw)
                if raw
                else {}
            )

            if self.path == "/api/investigations":
                result = investigate(
                    request, prices=PRICES, fits=ALL_FITS, as_of=AS_OF,
                    formation_observations=FIT_PAYLOAD["formation_observations"],
                )
                self.send_json(200, result)
                return

            result = scan(
                corr_min=float(
                    request.get(
                        "corr_min",
                        0.65,
                    )
                ),

                alpha=float(
                    request.get(
                        "alpha",
                        0.05,
                    )
                ),

                entry=float(
                    request.get(
                        "entry",
                        1.5,
                    )
                ),
            )

            self.send_json(
                200,
                result,
            )

        except Exception as exc:
            self.send_json(
                400,
                {
                    "error":
                        str(exc)
                },
            )


    def log_message(
        self,
        format,
        *args,
    ) -> None:
        print(
            "[anomaly-api]",
            format % args,
        )


if __name__ == "__main__":
    print()
    print("CLAIMGRAPH ANOMALY API")
    print("=" * 50)

    print(
        "SECURITIES:",
        PRICES["ticker"].nunique(),
    )

    print(
        "PAIR FITS:",
        len(ALL_FITS),
    )

    print(
        "AS OF:",
        AS_OF,
    )

    print(
        "CACHE DOMAIN:",
        f"corr >= {CORR_FLOOR},",
        f"p < {ALPHA_CEILING}",
    )

    print()
    print(
        f"http://{HOST}:{PORT}"
    )

    ThreadingHTTPServer(
        (HOST, PORT),
        Handler,
    ).serve_forever()
