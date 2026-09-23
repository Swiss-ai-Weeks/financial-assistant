# Pythia

*The oracle for a trading desk: it tells you what you missed, what you are
looking at, and what to look at next, and it shows its evidence.*

**When a strategy stops working, the reason is usually in the news. This desk
finds it and shows its evidence.**

A portfolio manager's book lagged its benchmark last month. The desk shows
*where* each trading strategy's assumption broke, lines those moments up against
the news that was public **at the time**, and asks a locally served NVIDIA
Nemotron model to explain each one with claims that are quoted, sourced and
auditable.

```
book vs benchmark ─► strategy monitors ─► anomaly ─► point-in-time news ─► Nemotron ─► ClaimGraph
   "I'm -2.6%"        VWAP · TWAP ·        "BAC/JPM       only what was       claims,      who said what,
                      trend · pairs        spread -3.4σ"   published before    hypotheses,  what supports,
                                                           the move            relations    what is missing
```

## Architecture at a glance

The diagrams below are generated from the LikeC4 model in `docs/architecture` and show the implemented system from the broad landscape down to the investigation runtime and backend code boundaries. Start with the overall system view, then follow a single ClaimGraph investigation through the components that execute it.

### System landscape

This is the top-level view of Pythia / ClaimGraph: the analyst-facing interfaces, backend and domain layers, persisted state, model runtime, search, market data, filings and news providers.

<p align="center">
  <img src="docs/architecture/assets/index.png" alt="Pythia / ClaimGraph system landscape" width="100%" />
</p>

### Investigation pipeline

This follows one ClaimGraph investigation end to end: from the UI request through anomaly resolution, point-in-time evidence retrieval, SEC fundamentals and the LLM claim / hypothesis stages, into the deterministic graph build and interactive inspection.

<p align="center">
  <img src="docs/architecture/assets/investigation_pipeline.png" alt="ClaimGraph investigation runtime pipeline" width="100%" />
</p>

### Investigation components

This view isolates the components that participate in an investigation, making the boundary between the React UI, FastAPI services and repositories, domain modules, state, model runtime and external evidence sources explicit.

<p align="center">
  <img src="docs/architecture/assets/investigation_components.png" alt="ClaimGraph investigation components" width="100%" />
</p>

### Backend modules

This is the code-oriented view of the implemented backend architecture, showing the controller → service → repository layering alongside the domain packages and external dependencies they use.

<p align="center">
  <img src="docs/architecture/assets/backend_modules.png" alt="Pythia implemented backend architecture" width="100%" />
</p>

## Quick start

Requires Python 3.11+ and Node 20.19+.

```bash
make setup     # virtualenv, Python and npm dependencies, .env
make dev       # API on :8080, UI on http://localhost:5173
```

That is the whole desk: live prices, the four strategy monitors, pair scans and
the news wire need **no API key and no GPU**.

News comes from eight interchangeable providers. Two need no key: Yahoo Finance
(the latest weeks) and [GDELT](https://www.gdeltproject.org/) (back to 2017,
heavily rate limited, archive only). Six are switched on by putting their key in
`.env`: [Finnhub](https://finnhub.io/) (ticker-tagged, with summaries, one year
back, US symbols), [EODHD](https://eodhd.com/) (also non-US listings),
[Marketaux](https://www.marketaux.com/), [GNews](https://gnews.io/),
[NewsAPI](https://newsapi.org/) and [Alpha Vantage](https://www.alphavantage.co/).
A SearXNG instance (`SEARXNG_URL`) is read as one more source.

The desk never waits for them. Everything a provider returns is accumulated in
`data/cache/news/<TICKER>.json`; a ticker with anything cached is answered from
disk at once and refreshed behind the request, and only a ticker seen for the
first time waits for its first fetch. Providers are asked concurrently and fail
independently. Because free tiers are counted in requests per day, each provider
has a refresh interval per ticker and a daily request budget, recorded in
`data/cache/news/_meta.json` so that restarting the desk does not spend the quota
again. `GET /api/news/sources` shows, per provider, whether it is configured, its
last success or error and what it has spent today; `POST /api/news/{ticker}/refresh`
asks every provider again, now.

Historical news is downloaded once into a local archive and replayed from disk,
so a recorded demo is reproducible. `make news` uses every configured provider,
then GDELT.

```bash
make news                        # the book, current review window (resumable)
make news ARGS="--universe"      # also pair partners from the peer universe
```

To replay a past month, pick the date in the top bar (**LIVE / REPLAY**): later
prices and later news stop existing for the whole desk until you press TODAY.
`AS_OF=2026-02-27` in `.env` starts the desk on that date; run `make news` for
the window you replay.

The **Explain** button needs a language model. On the GPU box:

```bash
pip install vllm
make llm       # Nemotron 3.5 Lightning 30B-A3B, one replica per H100, :8000
make search    # optional: SearXNG for wider web retrieval, then set SEARXNG_URL
```

Compare models on the same anomaly: **Apertus**, the Swiss AI Initiative's fully
open model, is offered next to Nemotron. `make apertus` serves it on the GPU
box (port 8001), or set `APERTUS_API_KEY` to use a hosted gateway. More models go
in `PYTHIA_MODELS`. See [Model and serving](#model-and-serving).

```bash
make universe  # once: prices for the 3,200-security universe (Russell 2500 + STOXX 600)
```

Set `SEC_USER_AGENT="Pythia research you@example.com"` and every investigation
also reads the quarterly SEC figures that had been filed by the evidence cutoff.

No GPUs at hand? Put an NVIDIA API key in `.env` (see `.env.example`) to use the
same model hosted. Other targets: `make test`, `make serve` (UI and API as one
process), `make reset` (restore the demo book), and **`make warm` before a demo**:
it pre-builds the slow caches, so the first 🍀 click is instant instead of
taking minutes.

## Three stories, one loop

The same engine (relationships → anomalies → evidence → analogues) answers three
questions. They are the first three icons of the left rail.

| | Question | What the desk shows |
|---|---|---|
| **Past** · post-mortem | *What did I miss?* | Findings ranked by money lost **after a signal was already visible**. Relationships that broke come first: "BAC underperformed JPM by 2.8% since Sep 15, 3.4σ outside their historical relationship", portfolio impact, what a hedge would have changed, the signal you could have seen, why the two are related, likely explanation and evidence confidence. |
| **Now** · copilot | *What is happening to this stock?* | A horizon slider (1D · 1W · 1M · 3M · 1Y) that changes the **interpretation**, not the zoom: abnormal return against a market model, volume, which historical peers did *not* follow, and what usually happened next in comparable situations. Reachable from any web page through the [Chrome extension](extension/README.md). |
| **Next** · discovery | *What should I be looking at?* | **I'm Feeling Lucky** inverts the pipeline: universe → possible relationships → co-moving → cointegrated → unusual → liquid → **Nemotron drops justified repricings** → favourable in out-of-sample analogues → **new to you** → one setup, with what would invalidate it and a button to the reasoning. |

All three end in the same place: **Explain** reads the news that was public at
the time, and the **ClaimGraph** shows why two things are connected and what the
evidence supports.

Two rules keep this honest. Every number in the discovery funnel is a real count
from that run, and every "what usually happens next" shows its sample size and
says *historical frequencies, not a forecast*. When nothing clears the bar, the
desk says so.

Three more views sit below the three stories in the rail:

| | Question | What the desk shows |
|---|---|---|
| **Book** · portfolio | *What did the book do, and what is researched?* | Returns, realised volatility, drawdown, concentration and 20-session contributors, each with its formula and input hash; research status per holding; the book edited as weights; a historical pair-overlay simulation (descriptive, never a forecast). |
| **Why** · ClaimGraph | *Why are these connected, and do the models agree?* | Every investigation opens as a **tab** that stays alive while you work elsewhere. Inside a tab: evidence filters, **time travel** through the evidence, a human **review** (accept / challenge / request evidence), **follow-up research** on any open question, a deterministic **report** (HTML/PDF, Markdown, JSON) and an advisory **Copilot** that can move the view but never the graph. **Compare models** lays the same anomaly side by side as read by Nemotron, Apertus or any configured model. |
| **Wire** · news graph | *What is being said about the book, and what did the model not expect?* | Every article read once into a temporal graph (securities, entities, typed events); a temporal graph network learns what normally comes next. A feed of canonical events, the graph of a security with the edges the model expects next, and per-day surprise and drift. See [Wire](#wire-the-news-graph-and-its-temporal-graph-network). |

Nothing reloads when you move between views: feeds, scans and graphs are
remembered (and survive a page refresh), then refreshed behind the scenes.

## The demo in five minutes

1. **Past.** The desk opens on *What you missed*: the book is −3.7% against SPY
   −0.7%, and the first finding is a relationship, not a loser.
2. Click it. News is split at the evidence cutoff into admissible and hindsight;
   **Explain with Nemotron** extracts quoted claims and weighs competing
   explanations. **Open ClaimGraph** to audit every step.
3. **Now.** On any finance page, highlight "Bank of America", right-click →
   *Analyse unusual activity*. Drag the horizon: unusual over a week (3σ),
   ordinary over a day, a month, a year. "JPM has not followed the move."
4. **Next.** Press 🍀. Watch 142 securities become 10,011 possible relationships
   become a handful of ideas the manager was *not* already looking at, then **Show me the
   reasoning**. Relationships involving a holding are listed apart: the
   post-mortem already reported them.
5. **Add a name.** Search a company in the top bar and press *Add*: the desk
   immediately tests it for cointegrated partners.
6. **Two readers.** In Explain, pick **Apertus** and explain the same anomaly
   again (or *Explain with every model*). **Why → Compare models** shows where
   the Swiss open model and Nemotron agree, and where a person should look.
7. **The hardware story.** The model pill in the top bar is green when the
   selected model is reachable, and every Explain shows measured latency per stage. Why
   this model, on this hardware: [Model and serving](#model-and-serving).

## Architecture

```
frontend/ (React + Vite)
    │  /api
    ▼
src/financial_assistant/api/          HTTP service (FastAPI)
    controllers/     HTTP in, HTTP out. No business rules.
    services/        Use cases and business rules. No HTTP, no disk, no network.
    repositories/    Everything that touches disk or the network.
    dependencies.py  Composition root: builds each object once, injects via Depends.
    │
    ▼
src/financial_assistant/              Domain. Knows nothing about HTTP.
    anomaly_detection/   pairs (cointegration) + VWAP, TWAP, trend detectors
    analytics/           abnormal returns per horizon, historical analogues
    market_data/         Yahoo Finance daily OHLCV
    retrieval/           news providers, article fetching, point-in-time eligibility
    fundamentals/        SEC Company Facts, as filed by the evidence cutoff
    research/            deterministic research planning
    llm/                 model registry + the model stages
    claimgraph/          typed investigation state -> auditable graph
    copilot/             the advisory chat panel of a graph tab
    portfolio/           versioned book analytics
    causal_scoring/      deterministic candidate scorer
    simulation/          hindsight-only pair trade replay
```

`controllers → services → repositories`, and services → domain; nothing points
the other way. Tests replace only the repository boundary (market download,
symbol search, news source, article fetcher, language model); controllers,
services and the ClaimGraph pipeline run for real (`tests/test_api.py`).

The three stories are three services on one engine: `PostMortemService` (past),
`MicroscopeService` (now) and `DiscoveryService` (next), over
`analytics/abnormal.py` (what is unusual, per horizon) and
`analytics/analogues.py` (what happened next in comparable past situations).

- **Discovery's causal stage is the model's.** Nemotron reads the top admissible
  headlines of every candidate (`llm/causal_triage.py`) and answers
  `lasting_event`, `transient_event` or `no_event` with the headline it rests
  on. Lasting events are dropped as justified repricings. Readings are stored
  under `data/state/triage/`, keyed by the anomaly and the exact headlines, so an
  unchanged desk replays them without a GPU.
- **Past and Next never show the same thing twice.** Discovery headlines only
  setups with no held leg; the others are listed as already on the desk.
- **Abnormal return** is the return a market model (beta on the previous 252
  sessions) does not explain, judged against daily abnormal volatility from the
  year *before* the horizon, scaled by √horizon.
- **Analogues** are past days on which a security (or a pair) stood as far from
  normal in the same direction over the same horizon, with a fully elapsed
  outcome. Relationship analogues are walk-forward: pairs are fitted only on
  data before each past date. Built once per universe, cached under
  `data/cache/analogues/`.

### Strategy monitors

Each strategy rests on one assumption. A monitor fires when it stops holding.

| Monitor | Assumes | Flags |
|---|---|---|
| VWAP | today's volume curve looks like history | volume > 3σ (log, 20d); close stretched > 2.5× typical from VWAP20 |
| TWAP | price does not drift while the order works | 5-session TWAP shortfall vs arrival price > 2.5× typical |
| Trend (MA cross) | a cross starts a persistent trend | MA7/MA25 crosses; whipsaw = reversed within 5 sessions |
| Pairs | the spread reverts to its mean | Engle-Granger cointegrated pairs with spread beyond 2σ |

All detectors are point-in-time: baselines use only sessions *before* the one
being scored.

### Pairs: how a relationship is found

- A pair is tested only when the daily log returns of its legs correlate
  ≥ 0.70 over the formation window (`PAIRS_CORR_MIN`). Every test is a chance of
  a false positive, so this filter is also the guard against flukes.
  `PAIRS_CORR_MIN_SAME_SECTOR` can set a looser bar within a sector.
- Both legs must be I(1) by ADF (unit root not rejected in levels, rejected in
  first differences, 5 %). Then Engle-Granger: OLS of log A on log B gives the
  hedge ratio beta, and ADF with AIC lag selection on the residuals is judged
  against MacKinnon's surface for two series (`PAIRS_ALPHA`). All of it is
  statsmodels' own (`adfuller`, `coint`, `OLS`).
- Engle-Granger is asymmetric, so both orderings are tested and the stronger is
  kept, with `ticker_a` as the dependent leg.
- beta is a ratio of **dollars**, not shares: $beta of B against each $1 of A.
- Relationships are fitted on **504 sessions** (24 months, `PAIRS_FORMATION`)
  before the review window, and beta and const never change inside it. Only
  the yardstick, the spread's mean and standard deviation, is re-estimated
  every 21 sessions from the trailing 252, from data strictly before the
  session judged (`PAIRS_RECALIBRATE_SESSIONS`, `PAIRS_RECALIBRATION_WINDOW`).
- Scans of more than a few dozen tests spread them over worker processes
  (`PAIRS_WORKERS`, every core by default). On an 11-core laptop: 2 s for 1,000
  names with 5 peers each, 30 s for 3,000 names with no peer limit.

### Universe

`data/universe/securities.json` is the catalogue: Russell 2500 and STOXX 600
**proxies** (holdings snapshots, not licensed index membership) plus the
hand-written large caps, about 3,200 securities. The Russell 2500 is US small
and mid caps: the ~500 largest US companies come only from the large-cap list.
`UNIVERSE_CATALOG=off` returns to the hand-written list.

- `make universe` fills the price cache in resumable chunks. The desk never
  downloads thousands of tickers inside a request; until `make universe` has
  run, scans cover whatever is already cached.
- `UNIVERSE_MAX` (default 1,000) bounds what is scanned: large caps, then names
  in the sectors of the book, then the rest. All 3,200 stay searchable.
- Above 400 securities, scans switch to `fit_large_universe`: pairwise-complete
  correlations (exchanges have different holidays), at most *K* peers per
  security before any test, pairs kept inside one universe and currency (a
  EUR/USD pair would be a bet on the exchange rate).
- Memberships are current snapshots: a replayed desk inherits today's
  survivors. Nothing claims point-in-time membership.

### Evidence cutoff

A daily bar becomes observable at the session close (21:00 UTC), the
**evidence cutoff** of an anomaly:

- published ≤ cutoff → *admissible*, may be used as evidence;
- published > cutoff → *hindsight*, shown dimmed, never sent to the model;
- undated → never admissible.

Evidence is organised around **key dates** (a relationship's onset and peak),
not recency: articles from the two days up to each key date lead the list.
Ordered by recency, AVGO/NVDA, which broke on Aug 19 and was detected on Sep
18, was explained from twelve Sep 18 articles and none of the 230 around its
onset. Fetched pages must also match their headline, because publishers answer
automated requests with consent walls that extract into clean, irrelevant text.

### Replay date

`AS_OF=YYYY-MM-DD`, or the date in the top bar (`PUT /api/system/as-of`), pins
the desk to a past session: `MarketDataRepository` hides later sessions and
`NewsService.window()` hides later news. For the pair monitor on a date D, the
review window is the 30 days ending on D, the relationship is fitted on the 504
sessions ending strictly before it, and every yardstick comes from sessions
before the one judged. `tests/test_point_in_time.py` replays the desk on D on
the true history and on one rewritten after D, and requires identical results.
A scan overtaken by a change of date is run again. A date with fewer than 504
sessions of history before its review window fits no pairs: raise
`HISTORY_DAYS` (1600) and run `make universe`.

GDELT and Yahoo are always merged because they fail in opposite directions:
GDELT reaches back to 2017 but its index lags about a week; Yahoo is precise
for the last few weeks and has nothing older. Replays more than a few weeks
back are GDELT-only in practice. What real GDELT downloads taught us is encoded
in `repositories/gdelt.py`: it matches text, not tickers; templated content
farms were 88% of results for a large bank; queries have an undocumented length
cap; the rate limit arrives as HTTP 429 *or* a 200 with a plain-text notice;
`seendate` is crawl time, which can only exclude evidence, never admit
hindsight.

### State on disk

```
data/seed/portfolio.json          the demo book, committed
data/universe/                    the security catalogue, committed
data/archive/news/*.jsonl         titles, summaries, URLs, timestamps
data/cache/documents/*.json       fetched article text (ignored: third-party content)
data/cache/market/daily/*.csv     OHLCV per ticker              (ignored)
data/cache/news/*.json            accumulated wire per ticker   (ignored)
data/state/                       edited book, investigations, triage (ignored)
```

`make reset` forgets the state and keeps the caches.

## Wire: the news graph and its temporal graph network

The sixth icon of the rail. Every article the wire brings about the book is
read once by Nemotron (title and summary, one short call) and becomes
timestamped edges: `security → entity` (who it was named with), `security →
event` (a canonical, typed event: earnings, guidance, M&A, regulation,
litigation, supply chain, customer, product, management, capital, analyst,
macro) and `security → event type`. The graph is one SQLite file
(`data/state/news_graph.sqlite`); an edge list with timestamps is a graph, and
what the desk needs most is time, which is an indexed range scan there.

A **temporal graph network** (Rossi et al. 2020; the PyTorch Geometric
implementation, the twitter-research data format) learns on that stream: every
node keeps a memory updated by its events, an attention layer over recent
neighbours gives an embedding at time *t*, and the model is trained to tell
real future edges from sampled ones, on a chronological split (70/15/15, never
shuffled, AP/AUC reported). Trained, it is replayed from the start and every
edge is scored *before* the model sees it. Per security and day that gives:

- **surprise**: one minus the probability the model gave the day's edges. High
  when a security is linked to something the graph never saw it with (a
  regulator, a new customer, a competitor). Not volume: structure.
- **drift**: how far the security's memory vector moved from its own trailing
  average. A narrative changing.
- **expected next**: the edges the model gives the highest probability for the
  coming week, drawn dashed red in the Graph tab. An expected edge that never
  comes is information too.

The page has three tabs: **Feed** (one row per canonical event, not per
article; commentary and recaps left out; filter by type or by "only what the
model did not expect"), **Graph** (the security at the centre, event types on
the inner ring, events and entities on the outer ring with time running
clockwise, solid edges lighter the more expected they were, predicted edges
dashed; click a node for the articles behind it) and **Signals** (surprise per
day, the day's largest surprise, drift). Everything is as of the desk's date.

The model ranks; it never explains. Its top items are candidates for Explain
and the ClaimGraph, which do the quoting. `make wire-evaluate` reports the lift:
how often a price shock (|daily log return| beyond 2σ of the trailing 60
sessions) follows a top-decile surprise day against any day, per security,
with sample sizes. Historical frequencies, not a forecast.

On the GPU box (reading articles is one Nemotron call each, minutes per call
on a hosted gateway, about a second on the local vLLM):

```bash
make news ARGS="--since 2025-09-22 --providers finnhub"   # a year of the book: ~15 min
make wire-ingest        # read every unread article into the graph: 1–3 h for a year
make wire-train         # the TGN, chronological split: minutes on one H100
make wire-score         # surprise, drift and expected edges into the store
make wire-evaluate      # lift against price shocks
make wire               # keep it current: refresh news, ingest, score, every 15 min
```

`make wire-ingest ARGS="--limit 200"` for a first look; `--as-of 2026-06-30`
on train and score for a point-in-time replay. `pip install -e ".[tgn]"` on a
machine without vLLM.

## Model and serving

The model is never asked whether an explanation is *true*. An investigation is
a fan-out of narrow, JSON-constrained tasks: claim extraction with a verbatim
quote (one call per article), competing hypotheses, a hypothesis audit,
relation assessment per hypothesis, and, in discovery, causal triage per
unusual relationship. Everything else is deterministic code: admissibility,
quote verification (the quote must occur literally in the article), verdict
tallies, the graph. A triage answer citing a headline that was not offered, or
was published after the anomaly, is discarded, never repaired.

**Why Nemotron 3.5 Lightning 30B-A3B:** 3B active parameters of 30B (mixture of
experts), so per-token cost is a small model's; hybrid Mamba-2 + attention, so
whole articles fit in the prompt; reasoning switchable per request (every stage
runs with `enable_thinking: false`); open weights served by us, so holdings and
questions never leave the machine; recommended by the hackathon instructors for
this hardware.

**On 2 × H100 80 GB:** BF16 weights are ~60 GB, so one GPU holds a full replica.
`make llm` runs **two replicas** (data parallel, one endpoint on :8000) rather
than one model sharded over both: requests are independent, so throughput
scales, there is no per-token all-reduce, and one replica keeps serving if the
other restarts. `LLM_TOPOLOGY=sharded` is only for contexts longer than one
GPU's KV cache. `--enable-prefix-caching` matters because every stage repeats a
long system prompt. The NVFP4 checkpoints target Blackwell; on Hopper we serve
BF16. Extra flags from the model card go in `VLLM_EXTRA_ARGS`.

**Hosted for development, local for recordings.** `LLM_PROFILE=hosted` uses
NVIDIA's gateway (`LLM_API_KEY` from <https://build.nvidia.com>);
`LLM_PROFILE=local` uses vLLM on the H100s. Saved explanations and triage
readings replay without a model, and every saved run records its provider and
model, so `make runs` proves a recording was produced locally. Before
recording: `make forget-runs`, `make warm`, then Explain the findings you will
show. The client adapts to hosted gateways instead of failing: a refused
optional field (HTTP 400/422) is dropped and the request retried, JSON is read
out of a `<think>` block or code fence when JSON mode is refused, 429s are
waited out, and `LLM_WORKERS=4` keeps free tiers from being flooded. Without
`LLM_API_KEY` the model shows **offline** rather than failing on first use.

**Apertus** (Swiss AI Initiative) sits next to Nemotron. `APERTUS_PROFILE=local`
(`make apertus`, port 8001) serves the 8B on the GPU with the most free memory,
in a fixed ~24 GB beside Nemotron; `APERTUS_SIZE=70b` takes both cards (tensor
parallel, ~140 GB BF16, or `APERTUS_QUANTIZATION=fp8`) and Nemotron cannot run
at the same time. `APERTUS_PROFILE=hosted` (with `APERTUS_API_KEY`) uses any
OpenAI-compatible host. More models go in `PYTHIA_MODELS`;
`LLM_EGRESS_POLICY=local_only` refuses every model not on our own network. Each
`ModelRun` records registry id, locality, latency, finish reason and reported
token counts; nothing is estimated.

## Running on the GPU box

```bash
git pull                   # or, on a fresh box: bash scripts/setup_gpu_box.sh
make llm                   # Nemotron on both H100s; first start downloads ~60 GB
make serve                 # the desk on ONE port, printed at start
make warm                  # once
```

`scripts/setup_gpu_box.sh` sets a fresh box up from a git bundle and a data
tarball (`data/archive/news`, `data/cache/analogues`, `data/cache/market`): it
checks the GPUs, clones, unpacks, installs dependencies and vLLM, and sets
`LLM_PROFILE=local`. `.env` is never copied: it holds API keys.

- **Opened in a browser** (VS Code web, NVIDIA Launchpad): use `make serve`,
  then **PORTS → Forward a Port** → that port → globe icon. The desk uses
  relative paths, so it works under a prefix like `/proxy/8081/`. `make dev`
  does not: its hot-reload server assumes it owns the host root.
- **Over SSH:** `ssh -L 8081:localhost:8081 <user>@<gpu-host>`, then
  <http://localhost:8081>.
- On the hackathon box, 8080 is the instance's own gateway (`openshell-gateway`,
  do not stop it). `make dev` and `make serve` take the first free port.
- Gated weights: `huggingface-cli login` first. If `make llm` rejects a flag,
  upgrade vLLM or pass the card's flags through `VLLM_EXTRA_ARGS`.

## Not yet verified on live services

Automated tests never leave the machine. Not yet exercised for real:

- an end-to-end investigation and a follow-up with a real model, in particular
  the larger prompts that include SEC context;
- Apertus itself: the hosted defaults and the vLLM flags in
  `scripts/serve_apertus.sh` were written from documentation;
- the keyed news providers (parsers are tested on fixtures);
- `make universe` and discovery over the full catalogue (timing, Yahoo rate
  limits).

## Event graph and source traceability

A planned EventKG-inspired layer would turn retrieved documents into atomic
claims, canonical events, and typed temporal relations before causal scoring.
It would add:

- conservative event identity resolution;
- lineage-aware claim fusion without erasing contradictions;
- immutable historical snapshots at a strict as-of time;
- evidence-backed economic paths from an event to a company or instrument;
- claim, relation, document, and policy IDs carried into the score result.

The design follows the [EventKG paper](https://arxiv.org/abs/1804.04526)
without RDF, SPARQL or a graph database. It is not in this branch's code yet
(there is no `event_graph` package); these are the rules it must keep. An
article is not a claim and a claim is not an event. The invariants that prevent
backtest leakage:

- timezone-aware timestamps everywhere; `retrieved_at` never precedes
  `published_at`, `extracted_at` never precedes retrieval;
- a historical snapshot rejects event metadata updated after its `as_of_at`;
  later claims appear only as opaque ignored IDs;
- a correction supersedes, but never deletes, its earlier claim;
- syndicated copies sharing a `lineage_id` count once; competing credible
  assertions stay `contested`;
- a relation needs at least one supporting claim, and a causal path uses only
  accepted relations valid at the replay time (no generic `related_to` edge).

Fusion weights by source role (primary 1.00, independent 0.80, secondary 0.50,
syndicated 0.35, market data 0.00) are versioned ranking heuristics, not
calibrated probabilities: change them only through a new
`FusionPolicy.version`. Every displayed signal must resolve through
signal → score → event snapshot → relations → claims → source documents, never
a rationale string alone.

## First contribution: causal candidate scoring

The package contains a deterministic scorer that ranks an event cluster as a
possible explanation for an observed price or volume anomaly.

The scoring unit is:

```text
(market anomaly, candidate event cluster, affected company)
```

It is deliberately **not an individual article**. Articles, filings, market
observations, and ontology facts are evidence for or against the event
hypothesis. This prevents ten syndicated copies of one wire story from looking
like ten independent confirmations.

The scorer returns:

- a 0–100 **rank score**, not a claimed probability of causality;
- an immutable snapshot of the policy and weights used to produce it;
- an eligibility and evidence-coverage status;
- every component score with rationale and evidence IDs;
- the complete source records referenced by those evidence IDs;
- contradictory-evidence strength;
- evidence ignored because it arrived after the causal cut-off;
- any caps caused by weak or missing core evidence.

## Criteria

| Criterion | Produced by | Meaning |
|---|---|---|
| Temporal fit | Scorer | Was supporting public evidence available before or during the anomaly? |
| Relationship directness | Ontology/model | How directly does the event connect to the company? |
| Economic plausibility | Model/human | Is there an explicit event → business driver → valuation mechanism? |
| Materiality | Model/financial rules | Is the effect large relative to the company's baseline? |
| Directional consistency | Market model | Does the mechanism's sign match the abnormal move? |
| Source independence | Scorer | How many original reporting lineages support it? |
| Primary-source support | Scorer | Is there a supporting filing, issuer release, regulator, or first-party report? |
| Novelty | Retrieval/embedding model | Is the event unusual relative to recent company events? |
| Market-footprint fit | Market model | Did the company and relevant peers move in the pattern the event predicts? |
| Contradictory evidence | Scorer | How strong are independent contradictory lineages relative to support? |

Semantic criteria may be proposed by an LLM, ontology service, market model, or
human. The LLM does not calculate the final score. Cut-off enforcement,
lineage deduplication, penalties, weighting, and classification remain
deterministic and testable.

## Default formula

```text
base =
    0.18 × temporal_fit
  + 0.14 × relationship_directness
  + 0.14 × economic_plausibility
  + 0.12 × materiality
  + 0.10 × directional_consistency
  + 0.08 × source_independence
  + 0.08 × primary_source_support
  + 0.06 × novelty
  + 0.10 × market_footprint_fit

score = 100 × max(0, base − 0.25 × contradiction_strength)
```

The defaults are versioned heuristics for ranking. They must be calibrated
against labelled historical replays before anyone interprets them as
probabilities.

## Usage

```python
from datetime import UTC, datetime

from financial_assistant.causal_scoring import (
    CandidateAssessment,
    CausalCandidateScorer,
    CriterionMethod,
    CriterionScore,
    EvidenceItem,
    EvidenceRole,
    EvidenceStance,
)

release = EvidenceItem(
    evidence_id="hp-release",
    source_name="HP Investor Relations",
    source_uri="https://investor.hp.com/",
    published_at=datetime(2024, 5, 29, 20, 5, tzinfo=UTC),
    lineage_id="hp-q2-2024",
    role=EvidenceRole.PRIMARY_SOURCE,
    stance=EvidenceStance.SUPPORTS,
)

market_close = EvidenceItem(
    evidence_id="hpq-market-close",
    source_name="Market data",
    published_at=datetime(2024, 5, 30, 20, 0, tzinfo=UTC),
    lineage_id="hpq-2024-05-30",
    role=EvidenceRole.MARKET_DATA,
    stance=EvidenceStance.SUPPORTS,
)

def judged(value: float, evidence_id: str) -> CriterionScore:
    return CriterionScore(
        value=value,
        rationale="Structured assessment with a traceable evidence item.",
        evidence_ids=(evidence_id,),
        method=CriterionMethod.MODEL_JUDGMENT,
    )

assessment = CandidateAssessment(
    anomaly_id="TECH-007",
    candidate_event_id="hp-q2-2024-results",
    anomaly_start_at=datetime(2024, 5, 30, 13, 30, tzinfo=UTC),
    anomaly_end_at=datetime(2024, 5, 30, 20, 0, tzinfo=UTC),
    as_of_at=datetime(2024, 5, 30, 20, 0, tzinfo=UTC),
    evidence=(release, market_close),
    relationship_directness=judged(1.0, "hp-release"),
    economic_plausibility=judged(0.9, "hp-release"),
    materiality=judged(0.75, "hp-release"),
    directional_consistency=CriterionScore(
        value=1.0,
        rationale="The expected and observed abnormal-return signs match.",
        evidence_ids=("hpq-market-close",),
        method=CriterionMethod.MARKET_MODEL,
    ),
    novelty=judged(0.8, "hp-release"),
    market_footprint_fit=CriterionScore(
        value=0.95,
        rationale="HPQ materially outperformed QQQ and relevant peers.",
        evidence_ids=("hpq-market-close",),
        method=CriterionMethod.MARKET_MODEL,
    ),
)

result = CausalCandidateScorer().score(assessment)
print(result.model_dump_json(indent=2))
```

## Safeguards

1. Supporting news first published after the anomaly cut-off is ineligible as a
   public-news cause.
2. A semantic value without evidence IDs is treated as missing.
3. A criterion that depends on post-cut-off evidence is discarded entirely.
4. Repeated syndicated stories sharing one `lineage_id` count as one source.
5. Missing temporal, relationship, or economic-plausibility evidence yields
   `insufficient_evidence`.
6. All timestamps must be timezone-aware.

For historical replay, set `as_of_at` to the simulated decision time. Never
attach later news or future prices to a criterion: the scorer will ignore the
late evidence, but upstream feature generation must also observe the cut-off.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The tests also run without pytest:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The Pydantic request and result models expose JSON Schema through
`model_json_schema()`. This keeps the core framework-independent while making
it straightforward to wrap as a typed NeMo Agent Toolkit function or a custom
workflow evaluator.
