# Pythia search and news restoration

The integration routed `/api/instruments/search` solely to `universe.search`, a substring search over `data/universe/securities.json`. The reference `InstrumentRepository` called `yf.Search` with a local fallback. CRWV was absent from the merged catalog, so removing that resolver made it disappear. Catalog membership never establishes the complete set of searchable securities.

`instruments.resolve` now merges catalog matches and Yahoo EQUITY/ETF quotes, normalizes ticker case, and deduplicates by Yahoo ticker identity. Canonical membership wins when both sources resolve the same symbol. Dynamic results have empty memberships, explicit resolution metadata, and independently reported market-cache / precomputed-pair coverage (unknown when not supplied). Nothing writes back to the catalog or an index. Yahoo failure preserves catalog results. Searchability does not guarantee cached market history or eligible pair fits.

The discovery wire composes precisely:

- Local `PYTHIA_NEWS_ARCHIVE` JSONL files (default `data/archive/news`), read on every request.
- Yahoo Finance ticker news, requested with `get_news(count=200, tab='news')`, accumulated in `PYTHIA_NEWS_CACHE` (default `data/cache/pythia_news`) and refreshed every 15 minutes per process/ticker. Cached stories remain readable during outages; availability is reported separately.

No BookReader, SearXNG, or NewsAPI results are added to this discovery feed. BookReader, SEC, web/search, market calculations, and optional archive retrieval remain in the existing ClaimGraph investigation pipeline. Explicit Investigate transfers the security/question/cutoff context, not the Yahoo feed. News ranking creates no graph relationships.

The API accepts `ticker` or comma-separated `tickers` (up to 30 for a portfolio), `as_of`, `days` (default 180, max 800), and `limit` (default 200, max 500 per temporal section). It returns `admissible`, `hindsight`, and a backwards-compatible `items` alias containing only admissible stories. Hindsight extends three days after the cutoff, matching the reference exploration window. Recent Yahoo cannot reconstruct historical coverage when neither archive nor accumulated cache has it.

Company aliases strip legal suffixes and avoid generic fragments such as “Bank” and “Bank of”. Case-insensitive whole-word title mentions rank above summary mentions, then ticker-tag-only stories; recency breaks ties. Story deduplication uses normalized headline plus UTC publication day. Publisher-direct URLs beat Finnhub redirects, then fuller summaries win. Copies retain all source provenance, maximum relevance, and the latest reported availability timestamp so merging cannot backdate a story.

Exact publication timestamps at or before cutoff are admissible by time, not admitted as evidence. Later stories appear only in the marked hindsight section. Date-only publication availability is conservatively end-of-day UTC. A date-only cutoff means end-of-day UTC, consistent with the existing desk API; callers requiring an exchange session close must supply that timestamp explicitly. Unknown/naive publication timestamps are excluded. Chart/session selection filters both displayed sections by UTC publication date.

## Deferred event triage seam

The reference causal triage was inspected, including its 12-headline bound, cutoff rejection and supplied-ID validation. Its model operation, verdict persistence, and provider composition are not present in the integrated discovery architecture. Reintroducing that model stage here would broaden this repair into model and lifecycle changes. Deterministic discovery is restored now; `admissible_headlines` supplies a bounded, cutoff-rechecked seam only. It performs no model call.

A future discovery/event triage implementation must use the existing ClaimGraph registry/router, cite only supplied headline IDs, reject invented/out-of-bound citations, exclude hindsight before invocation, and persist commentary separately from canonical evidence. It must not claim proof of causality or create support/weakening/contradiction edges. Onset/peak/latest balanced selection from the reference can be adapted when anomaly-specific triage is added.

## Live acceptance

With the existing API running on port 8001:

```bash
curl -fsS 'http://localhost:8001/api/instruments/search?q=CRWV'
curl -fsS 'http://localhost:8001/api/instruments/search?q=NVDA'
curl -fsS 'http://localhost:8001/api/news?ticker=CRWV&as_of=2026-09-21&limit=200'
curl -fsS 'http://localhost:8001/api/news?ticker=NVDA&as_of=2026-09-18T16:00:00Z&limit=200'
curl -fsS 'http://localhost:8001/api/news?tickers=NVDA,BAC&as_of=2026-09-21&limit=200'
```

CRWV requires Yahoo to resolve it; the response reports an outage without fabricating a result. On Now/Past, select a security, open News, select a chart session, and clear it. Check publisher, summary, source, full timestamp and separate hindsight. Investigate should open the usual question/model workspace without importing the wire. Existing Lucky behavior remains unchanged.

Offline reproducible fixtures cover CRWV-only lookup, catalog fallback/deduplication, archive/Yahoo merge, relevance, provenance, generous portfolio discovery, cutoff/date uncertainty, triage input bounds, and session filtering. Existing suites cover BookReader, evidence admission, investigations, routing, persistence, and Lucky. Browser acceptance uses isolated fixture APIs rather than live Yahoo.

## Validation results

- `.venv/bin/python -m pytest -q`: 271 passed. The sandbox initially blocked the demo-runtime socket test; the authorized rerun outside the sandbox passed.
- `npm --prefix frontend test`: 13 test files passed.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed; Vite reported a bundle above its 500 kB warning threshold.
- `git diff --check`: passed.
- `node frontend/tests/pythia.browser.cjs`: passed with the local fixture server and Chromium outside the sandbox. Covers date/session filtering, hindsight presentation, Yahoo outage messaging, dynamic CRWV selection/handoff, and existing model/workspace persistence flows.

Live Yahoo availability was not asserted by these deterministic tests. No commits, reference edits, model configuration changes, containers, or infrastructure changes were made.
