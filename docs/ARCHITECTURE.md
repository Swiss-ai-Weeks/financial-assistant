# Architecture

```
frontend/ (React + Vite)
    │  /api
    ▼
src/financial_assistant/api/          HTTP service (FastAPI)
    controllers/     HTTP in, HTTP out. No business rules.
    services/        Use cases and business rules. No HTTP, no disk, no network.
    repositories/    Everything that touches disk or the network.
    dependencies.py  Composition root: builds each object once, injects via Depends.
    models.py        What the desk stores (portfolio, news item, anomaly, investigation).
    schemas.py       Request / response bodies.
    │
    ▼
src/financial_assistant/              Domain. Knows nothing about HTTP.
    anomaly_detection/   pairs (cointegration) + VWAP, TWAP, trend detectors
    market_data/         Yahoo Finance daily OHLCV
    retrieval/           search providers, article fetching, point-in-time eligibility
    research/            deterministic research planning
    llm/                 provider + the four model stages
    claimgraph/          typed investigation state -> auditable graph
    causal_scoring/      deterministic candidate scorer
    simulation/          hindsight-only pair trade replay
```

## Dependency rule

`controllers → services → repositories`, and services → domain. Nothing points
the other way. A controller never opens a file; a repository never decides
anything.

Tests replace only the repository boundary (market download, symbol search, news
source, article fetcher, language model). Controllers, services and the
ClaimGraph pipeline run for real: see `tests/test_api.py`.

## Services

| Service | Responsibility |
|---|---|
| `PortfolioService` | The book: value, return vs benchmark, contribution per holding. Adding a holding triggers a focused pair scan. |
| `MarketService` | Quotes, candles, and the strategy reference lines (MA7/MA25, VWAP20, TWAP5). |
| `AnomalyService` | Runs the four strategy monitors over the review window; resolves a blotter row back to the neutral `AnomalyEvent`. |
| `NewsService` | Ticker and book wire; news around an anomaly, split at the evidence cutoff and ranked by relevance. |
| `InvestigationService` | Background ClaimGraph pipeline over admissible news, with per-stage progress. |

## Strategy monitors

Each strategy rests on one assumption. A monitor fires when it stops holding.

| Monitor | Assumes | Flags |
|---|---|---|
| VWAP | today's volume curve looks like history | volume > 3σ (log, 20d); close stretched > 2.5× typical from VWAP20 |
| TWAP | price does not drift while the order works | 5-session TWAP shortfall vs arrival price > 2.5× typical |
| Trend (MA cross) | a cross starts a persistent trend | MA7/MA25 crosses; whipsaw = reversed within 5 sessions |
| Pairs | the spread reverts to its mean | Engle-Granger cointegrated pairs with spread beyond 2σ |

All detectors are strictly point-in-time: baselines use only sessions *before*
the one being scored, and pair relationships are fitted on the 252 sessions
before the review window and never re-estimated inside it.

## Temporal provenance

A daily bar becomes observable at the session close (21:00 UTC). That instant is
the **evidence cutoff** of an anomaly:

- published ≤ cutoff → *admissible*, may be used as evidence;
- published > cutoff → *hindsight*, shown dimmed, never sent to the model;
- undated → never admissible.

Fetched pages must also match their headline, because publishers answer
automated requests with consent walls that extract into clean, irrelevant text.

## News: download once, replay from disk

```
make news ──► GdeltClient ──► data/archive/gdelt/<TICKER>.jsonl     (network, throttled, resumable)
desk      ──► GdeltNewsSource ──► reads the archive                 (no network, ever)
Explain   ──► CachedDocumentFetcher ──► data/cache/documents/*.json (fetched once, then replayed)
```

GDELT allows one request every five seconds and caps each at 250 articles, so
it cannot sit behind an interactive desk. `make news` downloads the desk's news
window in calendar-aligned weekly slices, records finished slices in
`manifest.json`, and can be interrupted and resumed. The desk "fetches" news as
it would live, from files that no longer change.

Things learned from real downloads, encoded in `repositories/gdelt.py`:

- GDELT matches text, not tickers: the query is the written company name plus
  finance terms.
- Templated content farms were 88% of results for a large bank. They are
  excluded in the query (they would otherwise fill the 250 cap) and again on
  read.
- Queries have an undocumented length cap, so exclusions are added worst-first
  up to a budget.
- The rate limit arrives as HTTP 429 *or* as HTTP 200 with a plain-text notice.
- `seendate` is when GDELT crawled the page, not when it was published. It can
  only be later, so it may exclude evidence but can never admit hindsight.

### Replay date

`AS_OF=YYYY-MM-DD` pins the desk to a past session. `MarketDataRepository` hides
later sessions and `NewsService.window()` hides later news; every detector is
already point-in-time relative to the latest session it is given, so nothing
else changes.

GDELT and Yahoo Finance are always merged, because they fail in opposite
directions: GDELT reaches back to 2017 but, when measured, its index had nothing
newer than about a week; Yahoo has precise timestamps for the last few weeks and
nothing older. Replay dates more than a few weeks back are therefore GDELT-only
in practice.

## State on disk

```
data/seed/portfolio.json          the demo book, committed
data/archive/gdelt/*.jsonl        GDELT titles + URLs + timestamps, committable
data/cache/documents/*.json       fetched article text, replayed (ignored: third-party content)
data/state/portfolio.json         the edited book            (ignored)
data/state/investigations/*.json  one replayable file per run (ignored)
data/cache/market/daily/*.csv     OHLCV per ticker            (ignored)
data/cache/news/*.json            accumulated wire per ticker (ignored)
```

`make reset` forgets the state and keeps the caches.
