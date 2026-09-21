# Pythia / ClaimGraph integration

## Inspection and authority

Inspected both repository trees, frontend entry points, navigation, styles, market and story components, API controllers/services/repositories, domain contracts, retrieval adapters, universe files, persistence, model routing, Copilot, graph inspection, and test organization before implementation. Target began clean on `feature/true-time-travel`, HEAD `7af643a` (model routing and Copilot). Reference is read-only. No merge, infrastructure changes, model provisioning, or commits.

ClaimGraph: React/Vite, React Flow, History API workspace reducer and browser storage; threaded Python API in `scripts/anomaly_api.py`; typed ClaimGraph nodes/edges; historical fitting; SEC quarterly fundamentals; BookReader + web composite retrieval; evidence assessment and bounded missing-evidence follow-up; registry/router and advisory Copilot. Its portfolio is a weighted analytical workspace, with deterministic returns and simulation. Graph snapshots and selected models belong to individual mounted investigation components.

Pythia: React/Vite financial desk, cream/ink/gold typography and left rail, top security selection, bottom tape, chart/blotter and right-hand context. Past is portfolio postmortem, Now is a horizon microscope, Next is discovery, Why is a graph. FastAPI controllers compose separate portfolio/market/news/investigation services and disk repositories. Market downloads, four strategy monitors, abnormal-return analytics, historical analogues, news archive, relevance ranking, and LLM headline triage underpin the stories. Pythia has no frontend automated test suite; Python tests cover its domain/services.

## Selective reuse

Reuse Pythia design tokens, icons, tab component and horizon analytics; adapt its rail, chart/blotter/context layout and current/historical story concepts to the existing API. Preserve selectable sessions, security search, horizon readings, anomalies, news candidates and explicit investigation entry points. Portfolio remains ClaimGraph's single reducer/API, rather than Pythia's separate quantity-based disk book. The interactive graph, NodeInspector, review, temporal inspection, missing evidence, model registry, execution metadata and Copilot remain ClaimGraph authority.

Do not port discovery's hard-coded model narration, headline-based causal exclusion, implied expected returns, or a second investigation engine. Discovery uses existing anomaly scans and canonical security search; microscope adds deterministic Pythia horizon measurements when cache coverage permits. No duplicate pairs/anomaly API is needed. News archives are optional retrieval candidates, never support merely because they are relevant. Pythia's download/warming/container scripts are not adopted.

## Frontend and workspaces

Primary product: PYTHIA. Main rail in order: NOW `/now`, PAST `/past`, PORTFOLIO `/portfolio`, EXPLORE `/explore`, INVESTIGATE `/investigate/:id` (with `/investigate` landing). Now reads latest cached market context and labels the actual date; Past explicitly chooses a cutoff and recomputes scans. Explore combines universe discovery with existing opportunity simulation. Holding → market context → investigation and anomaly → investigation are explicit actions.

Preserve `claimgraph:workspace:v1`; each investigation remains keyed and mounted when hidden. Tabs appear inside Investigate only. Add active-workspace restoration rather than always choosing the last tab. Existing graph/model snapshots, review storage and graph-position keys survive. Registry-backed analysis selection stays compact; a recorded execution model is distinct from the selected model for the next run. No frontend model-name constants.

## Backend/API and universe

Keep the existing server and all existing endpoints. Add thin read-only desk endpoints for instrument search, market candles/tape, microscope and archive candidate news; reuse `/api/anomalies/scan`, `/api/anomalies/historical-scan`, and `/api/portfolio/*`. Domain functions remain independently testable without starting a server or LLM.

Merge mapped ClaimGraph global CSV and both repositories' text universes into one canonical security catalog. Yahoo ticker is the strongest common existing identifier; retain suffixes/share classes and do not invent ISINs. Preserve all source rows, exchange/name/sector/currency, memberships and source filenames. Original source inputs are provenance; all runtime consumers use the same catalog/projection, not separate populations. Unmapped equities remain unresolved source records rather than fake tradable identities. Membership is `current_snapshot`, snapshot effective date unknown; no inferred S&P/Nasdaq memberships. Historical results explicitly disclose current-universe survivorship and do not claim point-in-time membership.

## Retrieval and provenance

BookReader remains in initial and follow-up retrieval, with server-side configuration and the existing document viewer. Optional Pythia JSONL archive adapter supplements the same composite search/fetch boundary. Preserve publication precision and cutoff eligibility; archive title/summary is a search candidate and must pass document extraction and evidence assessment. Keep SEC and market calculations unchanged. Epistemic provenance (source/dependency/support edges) and execution provenance (model_run/tool_call/agent_action/research_task) stay separate in graph and report.

## Copilot / CopilotKit

Existing presentation calls `askCopilot` with bounded `buildCopilotViewContext`; backend `/api/copilot` owns deterministic interaction/analysis/frontier routing and egress. `applyCopilotAction` validates UI targets. Commentary cannot add graph objects. Explicit analytical requests use the existing investigation/follow-up handler.

Deliberately defer CopilotKit runtime installation. Verified current official V2 documentation on 2026-09-21: https://docs.copilotkit.ai/reference/v2 and https://docs.copilotkit.ai/reference/hooks/useFrontendTool and https://docs.copilotkit.ai/react-spa . Future adapter: `CopilotKitProvider` and Sidebar/Chat from `@copilotkit/react-core/v2`, with a separate AG-UI endpoint translating messages into the existing Copilot request/response contract. Register only validated navigation tools through V2 `useFrontendTool` (Zod schemas); shared state is the bounded ViewContext, never writable canonical graph state. Human confirmation of an investigation calls the existing pipeline. Do not use the V1 compatibility `CopilotKit` wrapper or a generic built-in reasoning agent. Browser voice remains optional in the current panel.

## Reports

Deterministic `InvestigationReport` projection from completed canonical graph state; no LLM request and no chat rewrite. Include metadata/security/question/cutoff, claims/hypotheses, support/counter relationships, observations, calculations, inferences, assumptions/confounders, unresolved requirements, source appendix and separate execution appendix. Every statement retains node/edge/source identifiers. Temporal exclusions remain visible as exclusions, never promoted to evidence. Printable HTML (browser PDF), Markdown and JSON exports, with graph inspection links in the on-screen report. Report action belongs inside each investigation.

## Expected files

- This document; README acceptance notes.
- `frontend/src/WorkspaceShell.jsx`, `WorkspaceShell.css`, `workspaceStore.js`, `App.jsx`, `DetectorPanel.jsx`, `copilotContext.js`, `index.css`; `frontend/index.html`.
- New `frontend/src/pythia/` tokens/icons/tabs/desk components, desk client, styles.
- New `frontend/src/investigationReport.js`, `InvestigationReport.jsx` and focused frontend tests.
- New `src/financial_assistant/universe.py`, `desk.py`, `analytics/abnormal.py`, optional `retrieval/archive.py`.
- `scripts/anomaly_api.py`, historical scan metadata, universe consumer scripts, initial/follow-up retrieval composition.
- Canonical `data/universe/securities.json` plus reproducible merge script; no credentials or private archive content.
- Focused Python tests for catalog merge, temporal desk behavior, archive adapter; adapted Pythia analytics tests where applicable.

## Validation plan

Full existing Python and Node suites, lint, production build, `git diff --check`. Add union/multi-membership/current-only tests, desk cutoff/no-lookahead tests, navigation/workspace/model-isolation contracts, report identifier/category/export tests. Existing BookReader, Copilot target validation/no mutation and missing-evidence tests remain. Attempt browser validation if tooling is available; distinguish offline checks from live source/model acceptance. No LLM/container changes.

## Implemented outcome

Pythia is the primary shell with **NOW / PAST / PORTFOLIO / EXPLORE / INVESTIGATE** in that order. Now uses the latest cached session and visibly labels it (not a live-price claim). Past offers an explicit cutoff, price sessions, recomputed historical pairs and portfolio contribution context. Both expose horizon microscope readings, pre-horizon peer comparisons, VWAP/TWAP/trend monitors and archive candidates. Chart session selection filters the news view. Explore searches the canonical universe and retains the original anomaly/simulation workspace. The bottom tape uses the same portfolio plus cutoff-aware market calculations.

Actual reused files from Pythia: design tokens, stroke icons, Tabs, `analytics/abnormal.py`, `anomaly_detection/signals.py`, and focused tests for those analytical functions. The top bar, rail, desk, tape and report are adapted components over ClaimGraph state/APIs. Abnormal peer correlations now compute only against the subject rather than a full pairwise matrix. The existing weighted portfolio, simulator, SEC calculations, ClaimGraph/NodeInspector, review/time travel, missing-evidence pipeline, registry/router, and Copilot remain authoritative.

Security research has an explicit `security` mode for non-held prospects; it uses the existing human-research pipeline and never adds the security to the portfolio. Selected single-name monitor events are recomputed server-side at their date before becoming neutral attention events. They are not client-authored causal claims. The security, candidate cutoff and portfolio snapshot are captured when opening a tab, rather than borrowing a later global date.

### Canonical population

3,077 ClaimGraph symbols + 142 Pythia symbols − 26 overlaps = **3,193 securities**. Pythia contributes 116 additional symbols. Six unmapped source records remain explicitly unresolved. Multi-membership and all source rows are retained. `global_yahoo_tickers.txt` and its retry file contain no additional symbols beyond the merged population. The original CSV/text files remain source artifacts, not independent runtime catalogs. Identity/sector lookup, default market download, fitting, historical scans, search and follow-up peer policy use the canonical catalog. Explicit CLI subsets remain supported. Repeated pair memberships are deduplicated before historical monitoring and in newly generated live fit caches.

The current lists do not justify point-in-time index claims. Membership has `temporal_basis=current_snapshot` and `effective_date=null`. Historical peer enrichment still declines to assert a historical classification without valid-from data. Existing fit caches are not silently rebuilt; populate/recompute them explicitly to expand actual price/scan coverage.

### API organization

Existing `/api/investigations`, follow-up/status/models, Copilot, BookReader, anomaly scans and portfolio endpoints remain. New read-only projections:

- `GET /api/instruments/search?q=...`
- `GET /api/market/tape?tickers=COHU,PDFS&as_of=YYYY-MM-DD`
- `GET /api/market/{ticker}/candles?as_of=YYYY-MM-DD&days=180`
- `GET /api/market/{ticker}/signals?as_of=YYYY-MM-DD`
- `GET /api/microscope/{ticker}?as_of=YYYY-MM-DD`
- `GET /api/news?ticker=...&as_of=YYYY-MM-DD`

No duplicate discovery/pairs/investigation service: the existing scans supply discovery and pair candidates. Missing market cache no longer prevents the API from serving model registry, catalog, saved research or BookReader routes; market operations report unavailability. No infrastructure configuration was changed.

### Persistence, reports and Copilot

Investigation tabs appear only inside Investigate. Returning to it restores the active tab, not merely the newest one. Separate mounted components keep selection/filter/review/progress state while navigating; the existing localStorage graph/model snapshots and position/review keys remain. Browser reload restores graphs and workspace model choices; transient progress/selection is not a new persisted event log. Closing removes only that workspace.

Reports are deterministic projections at an explicit cutoff. Executive interpretation quotes existing inference/hypothesis objects, with identifiers; it does not synthesize new conclusions. Observations, calculations, inferences, assumptions, unresolved questions, source lineage, support/counter edges and execution records remain distinct. JSON includes the full canonical snapshot separately from cutoff-eligible report sections and lists temporal exclusions. HTML and Markdown include references and canonical detail; open the HTML export to Print / Save as PDF. Preparation is disabled while that workspace's investigation runs, and works with no configured/live LLM after loading a saved graph.

BookReader initial/follow-up search/fetch/viewer support remains intact, with configuration server-side. `PYTHIA_NEWS_ARCHIVE` optionally points to a local JSONL archive (default `data/archive/news`). Archive candidate hits join the same composite search and document-fetch/extraction/assessment flow; a summary is never admitted directly as support. Publication dates/precision, candidate identity and provider provenance survive. No reference archive content or credentials were copied. The existing bounded Copilot contract is unchanged; its panel is styled/positioned for Pythia and browser-tested for commentary without graph mutation. CopilotKit is deliberately deferred at the documented V2 presentation/AG-UI seam. No new runtime dependency is installed in the application.

## Remaining limits

- This checkout has no real market cache or Pythia news archive. Market results, source coverage and live BookReader/SEC/model availability require acceptance against the user's configured services. Automated tests use synthetic inputs or saved graphs; no live inference/private-source call was made.
- Pythia's historical analogue forecasts, automatic causal triage/ranking, separate disk portfolio, and separate investigation backend are deliberately not ported. Discovery is explicit security/pair exploration, not an autonomous opportunity ranker. The price chart is a lightweight interactive close-price chart, not the reference's full candlestick/spread chart package. Pairs retain the existing ClaimGraph candidate context and simulation.
- Daily cutoff policy remains ClaimGraph's conservative UTC end-of-day policy. No historical membership database, adjusted-price revision history, exchange calendar or FX engine is added. Microscope requires sufficient benchmark/volume history (SPY); missing data is unavailable rather than zero. No news archive download/warmer is run.
- Reports faithfully expose available canonical state, including incomplete evidence; they do not certify correctness or invent an investment recommendation. Browser storage has its existing quota limits. Report JSON can be larger because it contains the full graph.
- Production build emits a bundle-size advisory around 500 kB. No document framework, new application package, authentication, graph database, agent orchestration or infrastructure is introduced.

## Live acceptance commands

Use the existing configured services. The following commands start only the application processes if they are not already running; they do not provision or manage inference containers. Do not start duplicates if the existing demo is already serving these ports.

Terminal 1, backend (credentials remain only in this terminal/backend):

```bash
cd /home/codexdev/projects/claimgraph
source .venv/bin/activate
if [ -f .env.bookreader ]; then set -a; source .env.bookreader; set +a; fi
python scripts/anomaly_api.py
```

Terminal 2, frontend (fresh terminal; do not inherit the BookReader credential environment):

```bash
cd /home/codexdev/projects/claimgraph
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open `http://localhost:5173/now`, then `/past`, `/portfolio`, `/explore`, `/investigate`. For a completely offline graph/report acceptance, open Investigate → New investigation → saved illustrative review; inspect nodes, prepare report, export HTML/Markdown/JSON. Open a second tab, choose a different registry model, visit all other routes and return/reload. Confirm each workspace's graph/model remains isolated. Open Copilot and ask for a view explanation; ensure it remains commentary. For live acceptance, select a real cached security/event, explicitly run investigation, inspect model/source/calculation provenance, then select a missing-evidence node and run the existing follow-up.

Read-only API checks (a missing market cache can legitimately return unavailable):

```bash
curl -sS 'http://127.0.0.1:8001/api/health'
curl -sS 'http://127.0.0.1:8001/api/instruments/search?q=NVDA'
curl -sS 'http://127.0.0.1:8001/api/investigations/models'
curl -sS 'http://127.0.0.1:8001/api/market/COHU/candles?as_of=2026-03-20'
curl -sS 'http://127.0.0.1:8001/api/microscope/COHU?as_of=2026-03-20'
```

Rebuild catalog (reference stays read-only):

```bash
.venv/bin/python scripts/merge_security_universes.py --reference /home/codexdev/projects/teammate-pythia
```

Automated acceptance:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
```

Optional isolated Chromium acceptance, with Playwright outside application dependencies:

```bash
npm install --prefix /tmp/pythia-browser playwright
PLAYWRIGHT_BROWSERS_PATH=/tmp/pythia-browser/browsers /tmp/pythia-browser/node_modules/.bin/playwright install chromium
node frontend/tests/pythia.browser.cjs
```

It serves the production build on an ephemeral local port, mocks every API, checks all five routes, prospective-security handoff, inspector, workspace/model isolation, reload, advisory Copilot immutability and all three downloads. It captures desktop/mobile screenshots to `/tmp/pythia-{now,investigate,report,mobile}.png`. Socket/browser execution requires permission outside the filesystem/network sandbox.

## Validation results

- Full target Python suite: **265 passed**. All pre-existing tests retained; the historical HTTP route test now mocks the canonical catalog boundary instead of the retired direct CSV read.
- Frontend Node suite: **12 files passed**, including route/order, state/model isolation, report graph/source IDs, temporal exclusions, distinct observation/calculation/inference categories, exports without fetch/LLM, and invalid Copilot actions. Existing follow-up, fundamentals, temporal, Copilot and graph tests pass.
- ESLint: passed.
- Vite production build: passed (504.81 kB JS / 157.44 kB gzip; size advisory only).
- Isolated Chromium acceptance: passed, including all routes, graph inspector, prospective security handoff, independently selected models, navigation/reload persistence, commentary without canonical graph mutation, three downloaded report formats and mobile rendering. APIs were fixtures, not live financial claims.
- `git diff --check`: passed.
- Reference repository `git status --short`: empty. No commits, infrastructure changes, or model/container operations.

## Files changed

Modified:

- `README.md`
- `frontend/index.html`
- `frontend/src/App.jsx`
- `frontend/src/DetectorPanel.jsx`
- `frontend/src/WorkspaceShell.jsx`
- `frontend/src/workspaceStore.js`
- `scripts/anomaly_api.py`
- `scripts/download_market_history.py`
- `scripts/historical_api.py`
- `scripts/investigate_historical_pair.py`
- `scripts/investigation_api.py`
- `scripts/missing_evidence_followup.py`
- `scripts/precompute_demo_pairs.py`
- `src/financial_assistant/anomaly_detection/historical.py`
- `src/financial_assistant/fundamentals/service.py`
- `src/financial_assistant/research/identity.py`
- `tests/test_historical_scanner.py`
- `tests/test_time_travel_api.py`

Added:

- `data/universe/securities.json`
- `docs/pythia-claimgraph-integration.md`
- `frontend/src/InvestigationReport.jsx`
- `frontend/src/investigationReport.js`
- `frontend/src/pythia/MarketDesk.jsx`
- `frontend/src/pythia/MarketTape.jsx`
- `frontend/src/pythia/Tabs.jsx`
- `frontend/src/pythia/deskClient.js`
- `frontend/src/pythia/icons.jsx`
- `frontend/src/pythia/shell.css`
- `frontend/src/pythia/tokens.css`
- `frontend/tests/pythia.browser.cjs`
- `frontend/tests/pythia.test.js`
- `scripts/merge_security_universes.py`
- `src/financial_assistant/analytics/__init__.py`
- `src/financial_assistant/analytics/abnormal.py`
- `src/financial_assistant/anomaly_detection/signals.py`
- `src/financial_assistant/desk.py`
- `src/financial_assistant/retrieval/archive.py`
- `src/financial_assistant/universe.py`
- `tests/test_pythia_analytics.py`
- `tests/test_pythia_integration.py`
- `tests/test_pythia_signals.py`

Generated build/cache artifacts are ignored. Browser tooling and screenshots live in `/tmp`, outside application dependencies. The model registry/router, core graph schema/builders, NodeInspector, source adapters and Copilot reasoning contract were not replaced.
