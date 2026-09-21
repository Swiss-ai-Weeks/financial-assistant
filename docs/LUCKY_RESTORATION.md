# Pythia Lucky restoration

## Reference audit (read only)

Searched teammate-pythia comprehensively for `lucky`, `feeling`, `discovery`,
`random`, `surprise`, and `candidate`, including source, frontend, tests, docs,
fixtures and scripts. The feature is not a random ticker picker.

- `frontend/src/components/layout/SideRail.jsx`: **Next**, clover icon, title
  “Discovery: what should I look at?”. App's `discovery` view mounts
  `frontend/src/components/stories/DiscoveryView.jsx`.
- That component's hero says **What should I be looking at?**, with the visible
  button **I’m Feeling Lucky** (curly apostrophe), changing to
  **Scanning the universe…** while running.
- `api.startDiscovery()` posts `/api/discovery`; `api.discovery()` gets its
  background job, polled every 1.5 seconds. `story_controller.py` delegates to
  `DiscoveryService.start()` / `.job()`.
- `DiscoveryService.scan()` unions portfolio holdings and InstrumentRepository's
  configured universe, loads available prices, scans pairs and builds/caches a
  walk-forward analogue base. It requires correlation (with a lower within-sector
  threshold), cointegration, absolute deviation above entry, and minimum weaker-leg
  liquidity (mean close × volume over the last 20 sessions, in millions).
- Optional Nemotron triage reads cutoff-admissible, relevance-ranked headlines;
  verified lasting-event verdicts are excluded as justified repricings. Offline,
  failed or unverifiable readings do not exclude a candidate. Triage is cached.
- Survivors require analogue expected abnormal return > 0. They are sorted by
  **abs(z_score) × outcome.reversion_pct / 100**, descending. Pairs involving any
  holding are separated as “Already on your desk”; remaining pairs are all shown,
  with the first highlighted as “🍀 Today’s discovery”. There is no randomness.
- Cards show LONG/SHORT legs, deviation, analogue count, horizon, liquidity,
  anomaly summary, triage and cited headline, outcome frequencies, relationship
  statistics, invalidation conditions, evidence cutoff and a disclaimer.
- “Show me the reasoning” invokes App's `selectAnomaly`: selects the ticker and
  pair, moves to postmortem/Past, selects the spread and Explain pane. It does not
  itself run Explain or create a graph.
- `tests/test_api.py` covers funnel counts, exclusion of held pairs, analogue cache
  age/future safety, dropping justified repricings, offline cached replay,
  offline/invalid verdict handling, and background-job progress. No dedicated
  frontend Lucky test was found.

## Integrated behavior and adaptation

Explore (`/explore`, existing clover rail item) now starts with the original hero,
visible Lucky wording and clover. The hero/card CSS is derived from the reference
and uses the already restored Pythia theme tokens. Loading and empty-state wording
are retained. Directional LONG/SHORT recommendations are replaced by neutral pair
and inspect actions, in accordance with the discovery-only requirement.

`pythia/discovery.js` calls the existing `/api/anomalies/historical-scan` with the
shell cutoff and correlation .65, cointegration p .05, deviation 1.5 thresholds.
That endpoint uses the merged analytical universe and recomputes cutoff-safe fits;
no parallel universe, API service, model or infrastructure is introduced.
Returned candidates (the endpoint caps them at 50) are validated, ordered with
unheld pairs first, then descending absolute deviation and pair-name tie-break.
Both symbols must resolve exactly through `/api/instruments/search`, the current
canonical/Yahoo resolver. Unresolvable pairs are skipped. No random fallback or
invented security is supplied. Held-only results are labelled explicitly.

This adapts the original ranking: the current scan has no analogue-return base,
liquidity admission or discovery-specific model triage contract. Those stages
are not silently claimed or recreated. The result explicitly states that they
are not evaluated. The ranking is unusualness for research, not expected return.
Counts from unimplemented original funnel stages are not displayed.

Inspect opens the current Past security/market/news view at the same cutoff.
Either leg can be inspected. “Investigate discovery” passes the original candidate
(including historical scan id/mode) through the existing workspace opener. The
security's ordinary Investigate button remains available too. No Lucky action
calls inference, retrieval, graph mutation or evidence/support creation.

Unchanged: backend scanners, merged universe, resolver, Yahoo/archive newsflow,
market calculations, workspace reducer/storage, model routing and selections,
BookReader investigation retrieval, Copilot and ClaimGraph engine. Existing
historical scan expiry behavior is unchanged; opening a saved workspace does not
make its server scan cache permanent.

## Verification

`frontend/tests/discovery.test.js` exercises ordering, filtering, exact resolution,
held/empty/error handling, cutoff and payload preservation, allowed API calls,
explicit workspace handoff and graph/model persistence. Browser acceptance
locates the visible button, clicks it, checks the scan request, inspects both legs,
opens/reloads a persistent workspace, and repeats Lucky with saved graphs/models
present to verify they remain unchanged. It also checks no investigation or
follow-up inference endpoint was called.

Validation results: Python 271 passed; frontend 14 test files passed; ESLint passed;
production build passed (Vite reports a >500 kB bundle warning); browser acceptance
passed; `git diff --check` passed. Socket-dependent Python/runtime and browser
checks passed outside the sandbox after the sandbox denied local socket creation.
No models, containers or infrastructure changed. No commit created.
