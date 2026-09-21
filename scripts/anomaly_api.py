from __future__ import annotations

import json
import time
from historical_api import historical_scan
from bookreader_viewer import document_page, source_links
import re
from urllib.parse import urlparse, parse_qs, unquote

from investigation_api import investigate, public_models, investigate_missing_evidence
from investigation_progress import progress_registry

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

PRICES = pd.read_csv(PRICE_PATH) if PRICE_PATH.exists() else pd.DataFrame(columns=['date', 'ticker', 'close', 'volume'])

PRICES["date"] = pd.to_datetime(
    PRICES["date"]
)


print("Loading pair-fit cache...")

FIT_PAYLOAD = json.loads(FIT_PATH.read_text(encoding='utf-8')) if FIT_PATH.exists() else dict(fits=[], as_of='1970-01-01', corr_floor=.5, alpha_ceiling=.1, max_peers_per_ticker=5, formation_observations=252)


from financial_assistant.universe import universe_rows
UNIVERSE = pd.DataFrame(universe_rows())
UNIVERSE = UNIVERSE.loc[UNIVERSE["mapping_status"] == "mapped"].copy()


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


    if PRICES.empty or not FIT_PATH.exists():
        raise ValueError('Market / pair-fit cache unavailable; populate the existing cache to scan')
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
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = unquote(parsed.path)
        if path.startswith(('/api/instruments/', '/api/market/', '/api/microscope/', '/api/news')):
            try:
                from financial_assistant.universe import search, LIMITATION
                from financial_assistant.desk import market_view, microscope, signal_context
                from financial_assistant.retrieval.archive import archive_items
                as_of = query.get('as_of', [None])[0]
                if not as_of:
                    if PRICES.empty and not path.startswith(('/api/instruments/', '/api/news')):
                        raise ValueError('Market cache unavailable')
                    as_of = str(PRICES.date.max().date()) if not PRICES.empty else pd.Timestamp.now(tz='UTC').date().isoformat()
                if path == '/api/instruments/search':
                    result = dict(securities=search(query.get('q', [''])[0][:100]), limitation=LIMITATION)
                elif path == '/api/market/tape':
                    tickers = query.get('tickers', [''])[0].split(',')[:100]
                    from financial_assistant.portfolio.returns import security_returns
                    result = dict(as_of=as_of)
                    result['quotes'] = [dict(security_returns(PRICES,t,as_of), ticker=t) for t in tickers if t]
                elif path.startswith('/api/market/') and path.endswith('/candles'):
                    result = market_view(PRICES, path.split('/')[3], as_of, int(query.get('days', ['180'])[0]))
                elif path.startswith('/api/market/') and path.endswith('/signals'):
                    result = signal_context(PRICES, path.split('/')[3], as_of)
                elif path.startswith('/api/microscope/'):
                    result = microscope(PRICES, path.split('/')[3], as_of)
                elif path == '/api/news':
                    items = archive_items(ticker=query.get('ticker', [None])[0], as_of=as_of)
                    result = dict(items=items[:100], as_of=as_of, role='retrieval_candidates',
                        source='Pythia local archive', notice='News requires ClaimGraph assessment before it is evidence. BookReader remains available through investigation retrieval.')
                else:
                    self.send_json(404, {'error': 'Unknown desk endpoint'})
                    return
                self.send_json(200, result)
            except (ValueError, KeyError, IndexError) as exc:
                self.send_json(400, {'error': str(exc)})
            return
        if self.path.startswith("/api/bookreader/documents/"):
            try:
                body = document_page(self.path.removeprefix("/api/bookreader/documents/"))
            except Exception:
                self.send_json(400, {"error": "BookReader document unavailable or invalid identifier"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/bookreader/source-links":
            self.send_json(200, source_links())
            return
        if self.path == "/api/replays":
            packets = []
            for path in sorted(Path(".run/replays").glob("*.json"), reverse=True):
                try:
                    packet = json.loads(path.read_text())
                    if packet.get('followups'):
                        latest = packet['followups'][-1]
                        packets.append({'id': path.stem, 'label': f"{packet.get('ticker', 'Investigation')} · {latest['cutoff']} · missing-evidence follow-up"})
                        continue
                    meta = packet["historical"]
                    fit = meta["signal"]["fit"]
                    packets.append({"id": path.stem, "label": f"{fit['ticker_a']} / {fit['ticker_b']} · {meta['as_of']} · saved historical run"})
                except (ValueError, KeyError):
                    continue
            self.send_json(200, {"replays": packets})
            return
        if self.path.startswith("/api/replays/"):
            replay_id = self.path.removeprefix("/api/replays/")
            if not re.fullmatch(r"[a-f0-9-]{36}", replay_id):
                self.send_json(400, {"error": "Invalid replay ID"})
                return
            path = Path(".run/replays") / f"{replay_id}.json"
            self.send_json(200 if path.exists() else 404,
                           json.loads(path.read_text()) if path.exists() else {"error": "Replay not found"})
            return
        if self.path.startswith("/api/investigations/status/"):
            status = progress_registry.get(self.path.removeprefix("/api/investigations/status/"))
            self.send_json(200 if status else 404, status if status else {"error": "Unknown run"})
            return

        if self.path == "/api/investigations/models":
            self.send_json(200, public_models(check_health=True))
            return
        if self.path == "/api/health":
            self.send_json(
                200,
                {
                    "status": "ok",

                    "as_of":
                        AS_OF.isoformat() if FIT_PATH.exists() else None,
                    "market_as_of": str(PRICES.date.max().date()) if not PRICES.empty else None,
                    "cache_available": not PRICES.empty and FIT_PATH.exists(),

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
            not in ("/api/copilot", "/api/anomalies/scan", "/api/anomalies/historical-scan", "/api/investigations", "/api/investigations/followup", "/api/portfolio/analysis", "/api/portfolio/simulate", "/api/portfolio/market")
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

            if self.path == '/api/copilot' and not 0 < length <= 40000:
                raise ValueError('Copilot request exceeds the 40KB limit')
            raw = self.rfile.read(
                length
            )

            request = (
                json.loads(raw)
                if raw
                else {}
            )

            if self.path == "/api/copilot":
                from financial_assistant.copilot.service import copilot
                result = copilot(request)
            elif self.path in ('/api/portfolio/analysis', '/api/portfolio/simulate', '/api/portfolio/market'):
                from financial_assistant.portfolio.returns import analyze_portfolio, simulate_overlay
                if self.path.endswith('/market'):
                    from financial_assistant.portfolio.service import market_context
                    result = market_context(request['tickers'], request['as_of'], PRICES)
                elif self.path.endswith('/analysis'):
                    result = analyze_portfolio(PRICES, request['portfolio'], request['as_of'])
                else:
                    result = simulate_overlay(PRICES, request['portfolio'], request['candidate'], request['as_of'],
                                              request.get('gross_overlay', .02), request.get('lookback', 252))
            elif self.path == "/api/investigations/followup":
                result = investigate_missing_evidence(request)
            elif self.path == "/api/investigations":
                result = investigate(
                    request, prices=PRICES, fits=ALL_FITS, as_of=AS_OF,
                    formation_observations=FIT_PAYLOAD["formation_observations"],
                )
            elif self.path == "/api/anomalies/historical-scan":
                result = historical_scan(
                    request, PRICES, universe=UNIVERSE,
                    formation_observations=FIT_PAYLOAD["formation_observations"],
                    corr_floor=FIT_PAYLOAD["corr_floor"],
                    alpha_ceiling=FIT_PAYLOAD["alpha_ceiling"],
                    max_peers_per_ticker=FIT_PAYLOAD["max_peers_per_ticker"],
                )
            else:
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

        except Exception as exc:
            if self.path == '/api/copilot':
                self.send_json(400, {'error': str(exc) if isinstance(exc, ValueError) else 'Copilot failed',
                                     'code': getattr(exc, 'code', 'invalid_request')})
                return
            self.send_json(
                400,
                {
                    "error":
                        ("Follow-up failed; the original investigation is preserved"
                         if self.path == "/api/investigations/followup" else str(exc))
                },
            )
            return

        # Response delivery is separate from application execution errors.
        try:
            self.send_json(200, result)
        except (BrokenPipeError, ConnectionResetError):
            self.log_message(
                "%s completed but the client disconnected during response delivery",
                "Investigation" if self.path == "/api/investigations" else "Scan",
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
