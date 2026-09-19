# ClaimGraph Demo Runbook

## What this application does

ClaimGraph turns an unusual market observation into an inspectable
investigation.

The current demo flow is:

    BlackRock holdings universe
            ↓
    Yahoo Finance market observations
            ↓
    correlation / cointegration pair screening
            ↓
    anomaly candidates
            ↓
    human-configurable detector criteria
            ↓
    ClaimGraph investigation graph

The anomaly detector is an attention mechanism.

An anomaly means:

    "This relationship behaved unusually enough to investigate."

It does NOT mean:

    "We have established why this happened."


## Current market universe

The demo universe is based on holdings files downloaded from BlackRock:

- iShares Russell 2500 ETF holdings proxy
- iShares STOXX Europe 600 UCITS ETF holdings proxy

The holdings were mapped to Yahoo Finance tickers.

The current market cache contains approximately:

- 3,045 securities
- over 1 million daily observations
- data through 18 September 2026

Market data source:

    Yahoo Finance via yfinance


## Statistical pipeline

An exhaustive all-pairs search across ~3,000 securities would involve
more than 4.5 million pairs.

ClaimGraph therefore uses a bounded screening process:

    securities
        ↓
    return correlations
        ↓
    top correlated peers per security
        ↓
    Engle-Granger cointegration
        ↓
    frozen PairFit objects
        ↓
    current spread z-score

The current precomputed cache contains:

    624 fitted pair relationships

The expensive pair fitting is cached.

The user can then interactively change:

- minimum correlation
- maximum cointegration p-value
- anomaly z-score threshold


## Important files

Market observations:

    data/cache/market/global_demo_daily.csv

Precomputed pair relationships:

    data/cache/market/demo_pair_fits.json

Universe metadata:

    data/universe/global_equities.csv

Anomaly API:

    scripts/anomaly_api.py

Large-universe fitting:

    src/financial_assistant/anomaly_detection/scalable.py

Frontend:

    frontend/src/App.jsx

Detector controls:

    frontend/src/DetectorPanel.jsx

Graph renderer:

    frontend/src/ClaimGraph.jsx

Node inspector:

    frontend/src/NodeInspector.jsx


## Starting the demo

From the repository root:

    cd /home/nvidia/prototype/financial-assistant
    ./scripts/start_demo.sh

This starts:

    anomaly API     127.0.0.1:8001
    Vite frontend   127.0.0.1:5173

The processes are started with nohup and therefore survive an SSH
terminal disconnect.


## Checking the services

Backend health:

    curl http://127.0.0.1:8001/api/health

Frontend/API integration:

    curl http://127.0.0.1:5173/api/health


## Logs

Backend:

    tail -f logs/anomaly_api.log

Frontend:

    tail -f logs/frontend.log


## Stopping the demo

    ./scripts/stop_demo.sh


## Testing the anomaly detector directly

Permissive settings:

    curl -s \
      -X POST \
      http://127.0.0.1:8001/api/anomalies/scan \
      -H 'Content-Type: application/json' \
      -d '{
        "corr_min": 0.65,
        "alpha": 0.05,
        "entry": 1.50
      }' \
      | python3 -m json.tool

A recent reference run produced approximately:

    eligible relationships: 187
    anomalies:              26
    runtime:                ~0.5 seconds

A stricter configuration:

    corr >= 0.70
    p < 0.01
    |z| > 2.00

produced approximately:

    eligible relationships: 39
    anomalies:               2


## What currently works

- large market universe
- current cached market observations
- scalable pair pre-screen
- cointegration fitting
- anomaly calculation
- interactive detector thresholds
- candidate list
- ClaimGraph JSON visualization
- graph node inspection


## Current limitation

Selecting an anomaly candidate does not yet execute the entire
research pipeline automatically.

The graph initially displayed by the frontend is currently loaded from:

    frontend/public/investigation_live_nvidia.json

The detector on the left is live.

The investigation graph on the right is currently a prepared
investigation example.

The next integration boundary is:

    anomaly candidate
        ↓
    research plan
        ↓
    BookReader + web retrieval
        ↓
    claim extraction
        ↓
    generated ClaimGraph


## Rebuilding the pair-fit cache

This is NOT needed each time the UI starts.

Run it only when the market cache or universe changes:

    time python3 scripts/precompute_demo_pairs.py

A recent run took roughly 52 seconds and produced 624 fitted
relationships.


## External systems

They are not required merely to show the current UI.

NVIDIA NIM is required for LLM-backed research / claim generation.

BookReader is required for retrieval from the private newspaper corpus.

Yahoo Finance is required only when refreshing the market-data cache.

The normal UI startup should not depend on any of those external
services.
