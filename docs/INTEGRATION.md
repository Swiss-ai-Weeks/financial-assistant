# ClaimGraph integration

Pythia kept its desk (Past · Now · Next) and its look. This document lists what
was brought in from the ClaimGraph research branch (`feature/true-time-travel`),
how each piece was fitted to Pythia's controllers / services / repositories, and
what still has to be checked against live services.

## What was added

| Feature | Backend | Frontend |
|---|---|---|
| **Several models, compared** | `llm/model_registry.py`, `GET /api/investigations/models`, `model_id` on `POST /api/investigations` | model pill in the top bar, reader chips in Explain, **Why → Compare models** |
| **Apertus** (Swiss AI Initiative) | registry entry `apertus`, `scripts/serve_apertus.sh`, `make apertus` | offered everywhere a model is chosen |
| **SEC fundamentals** | `fundamentals/` (point-in-time Company Facts, quarterly), new pipeline stage | SEC block in Explain, quarter nodes in the graph, financial inspector |
| **Typed evidence assessment** | `llm/relation_assessment.py` + `llm/evidence_arguments.py` | relation inspector |
| **Missing-evidence follow-up** | `api/services/followup.py`, `POST /api/investigations/{id}/followups` | *Investigate this question* in the inspector, turn selector |
| **Copilot chatbot** | `copilot/`, `POST /api/copilot` | floating panel in every graph tab |
| **Portfolio workspace** | `portfolio/`, `GET /api/portfolio/analysis`, `POST /simulate`, `POST /market`, `PUT /weights` | **Book** view |
| **3,200-security universe** | `data/universe/securities.json`, `anomaly_detection/scalable.py`, `make universe` | search, pair scans, discovery |
| **News providers + cache** | Alpha Vantage, EODHD, Finnhub, GNews, Marketaux, NewsAPI, GDELT, Yahoo, SearXNG; stale-while-revalidate cache with per-source budgets; `GET /api/news/sources`, `POST /api/news/{ticker}/refresh` | source strip and Refresh in the News tab |
| **Time travel** | `api/clock.py`, `PUT /api/system/as-of` | LIVE / REPLAY date in the top bar; evidence timeline inside each graph |
| **Review, report** | none: both are projections of the graph | Review and Report panels in a graph tab |
| **State that stays** | investigations were already on disk | `lib/resourceCache.js`, `usePersistentState`, kept-alive views and tabs |

Deliberately **not** brought over: the BookReader newspaper corpus (the news
cache and the providers above replace it), the single-file threaded HTTP server,
and the client-side-only portfolio. The causal candidate scorer
(`causal_scoring/`) was already identical in both repositories; it still feeds
only the v1 graph builder.

## Models

Every investigation is read by exactly one model. The registry is built from:

1. the `LLM_PROFILE` model (Nemotron), which stays the default;
2. **Apertus**, unless `APERTUS_PROFILE=off`;
3. anything in `PYTHIA_MODELS` (a JSON list; see `.env.example`).

`APERTUS_PROFILE` decides where Apertus runs, the way `LLM_PROFILE` does for
Nemotron:

| Profile | Endpoint | Notes |
|---|---|---|
| `local` (default without a key) | `http://127.0.0.1:8001/v1`, `swiss-ai/Apertus-8B-Instruct-2509` | `make apertus`. Prompts stay on the machine. |
| `hosted` (default with `APERTUS_API_KEY`) | `https://api.publicai.co/v1`, `swiss-ai/apertus-70b-instruct` | Any OpenAI-compatible host works: set `APERTUS_BASE_URL` and `APERTUS_MODEL` (e.g. the Hugging Face router with `swiss-ai/Apertus-70B-Instruct-2509`). |

### Apertus on the two H100s

- **8B next to Nemotron** (default of `make apertus`): ~16 GB in BF16 on GPU 1.
  Start Nemotron on one card (`LLM_TOPOLOGY=single CUDA_VISIBLE_DEVICES=0 make
  llm`) or lower `APERTUS_GPU_MEMORY` if a Nemotron replica shares the card.
- **70B**: `APERTUS_SIZE=70b make apertus`. BF16 weights are ~140 GB, so it takes
  both cards (tensor parallel) and Nemotron cannot run at the same time.
  `APERTUS_QUANTIZATION=fp8` halves that. Then set
  `APERTUS_MODEL=swiss-ai/Apertus-70B-Instruct-2509` for the desk too.
- Apertus needs a vLLM built against transformers ≥ 4.56. It has no reasoning
  mode, so its registry entry uses `thinking_control: none` and nothing is sent
  that a server could refuse.

`LLM_EGRESS_POLICY=local_only` refuses every model that is not on our own
network, in investigations and in the Copilot alike.

Each `ModelRun` in a graph now records the registry id, locality, latency,
finish reason and, where the server reports them, token counts. The comparison
view sums them per run. Nothing is estimated: a server that reports no usage
shows "not reported".

## Investigation pipeline

```
news → documents → SEC fundamentals → claims → hypotheses → audit → relations → graph
```

- **SEC fundamentals** need `SEC_USER_AGENT` (EDGAR asks every client to name
  itself). Facts are selected by *filing date ≤ evidence cutoff*; responses are
  cached for 24 h in `data/cache/fundamentals`. Without the variable, or for a
  non-US issuer, the stage reports "unavailable", the graph records the gap as
  missing evidence, and the investigation continues on news alone.
- Hypothesis generation and audit read a bounded financial context
  (`FINANCIAL_CONTEXT_CHARS`). Relation assessment judges claims, observations
  and calculations alike, keeps the batches of four and the id-constrained
  schema, and selects at most 16 items per hypothesis so SEC volume cannot crowd
  out the articles. A figure is never attached as context by default.
- **Follow-up**: one cycle, started by a person on one Missing Evidence or
  Evidence Requirement node. It ranks the news cache (and SearXNG, when
  configured) against the question, reads up to five new documents, adds SEC
  figures if the graph has none, weighs the new evidence against the
  explanations concerned, and asks the model whether the question is answered.
  The graph gains the evidence *and* how it was found (`agent_action`,
  `research_task`, `tool_call`, `model_run`), kept apart from the evidence. One
  follow-up per investigation at a time; it never schedules another.

## Copilot

`POST /api/copilot` takes a question and a bounded projection of the view the
browser is showing (≤ 22 KB client side, ≤ 24 KB and schema-validated server
side). Routing is a keyword matcher plus the plane the person selected:
*Navigate* prefers a local interaction model and falls back to the workspace's
model, *Analyse* uses the workspace's model, *Second opinion* uses a model with
role `frontier` and only when asked for explicitly. The reply may carry one UI
action out of eight, checked against the ids that were on screen, first by the
server and again by the browser. It cannot add, change or resolve anything in
the graph; a suggested follow-up is a button a person has to press.

## Portfolio

The book stays Pythia's: share counts on disk, because every money figure on the
desk (impact, hedges) is in shares. The analytical workspace reads it as
market-value weights at the latest visible close. `PUT /api/portfolio/weights`
replaces the book from weights and a notional. Calculations are the versioned
ones of `portfolio/returns.py`; responses carry the input hash and observation
counts rather than every input price.

## Universe and pair scans

`data/universe/securities.json` is the merged catalogue (Russell 2500 and STOXX
600 proxies plus the original large caps): about 3,200 securities with name,
exchange, sector, currency and index snapshot. `UNIVERSE_CATALOG=off` returns to
the hand-written list.

- Search answers from the catalogue and from Yahoo; either alone is enough.
- The desk never downloads thousands of tickers inside a request. `make
  universe` fills the price cache in resumable chunks; interactive scans refresh
  only the book, the benchmark and the ticker on screen. **Until `make universe`
  has run, scans cover whatever is already cached** (the old ~140 names).
- Above 400 securities, scans switch from the exhaustive fitter to
  `fit_large_universe`: pairwise-complete correlations (different exchange
  holidays), at most *K* peers per security before any Engle-Granger test, pairs
  kept inside one universe and currency, both orderings tested.
- Discovery's walk-forward analogue record is built from the book and the
  securities that are related today (at most 160), not from the whole universe.
- Index memberships are current snapshots. A replayed desk inherits today's
  survivors; nothing claims point-in-time membership.

## State that stays

- `useResource` remembers every answer under its key. A key seen before is shown
  at once, whichever view asks, and is fetched again only when older than its
  `maxAge`. News, scans, the portfolio and the post-mortem are also persisted to
  `localStorage`, so they survive a reload of the page. Keys carry the replay
  date: another date is another set of answers.
- Finished investigations are cached the same way; opening a graph again is
  instant and verified in the background.
- Views (desk, Next, Book, Why) and graph tabs are mounted once and then hidden,
  not removed. Filters, evidence cutoff, selected node, turn and dragged node
  positions are remembered per investigation; view, ticker, tabs, open graphs
  and the chosen model are remembered across reloads.
- `/?mode=graph&open=<investigation id>` opens a graph directly.

## Acceptance still to do on live services

Automated tests never leave the machine (300 Python tests, 57 frontend tests,
lint and production build are clean). Not yet exercised against real services:

- an end-to-end investigation and a follow-up with a real model after these
  changes, in particular the larger prompts that include SEC context;
- Apertus itself: the hosted default (Public AI base URL and model name) and the
  vLLM flags in `serve_apertus.sh` were written from documentation;
- the five new keyed news providers (no keys were available; parsers are tested
  on fixtures; free-tier budgets are defaults that can be raised);
- `make universe` and a scan over the full catalogue (timing and Yahoo rate
  limits), and discovery on it.
