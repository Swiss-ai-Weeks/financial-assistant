# Portfolio workspace and Explore implementation

ClaimGraph now has three connected modes within the existing React application. The existing synchronous investigation, SEC fundamentals, BookReader/web retrieval, heterogeneous assessment, review, follow-up and hindsight pipelines remain in place. No new framework, database, ingestion system, optimizer, brokerage connection or authentication was added.

**Historical simulation is descriptive evidence about the selected historical sample. It is NOT an expected return forecast and NOT an investment recommendation.** This statement appears in Portfolio and Explore and in the simulation result contract.

## Files changed

- `frontend/src/WorkspaceShell.jsx`: navigation, shared context/reducer owner, Portfolio, Explore, holding/research links, explicit calculations, simulation and local persistence.
- `frontend/src/workspaceStore.js`: state transitions, sample portfolio, portfolio validation, holding research lookup and turn overlays.
- `frontend/src/WorkspaceShell.css`: website shell, graph canvas, floating controls and inspector drawer.
- `frontend/src/main.jsx`: mount the shell.
- `frontend/src/App.jsx`: retained investigation engine UI, isolated workspace inputs/model, graph snapshot reporting, follow-up card/history, simulation action and closable inspector.
- `frontend/src/ClaimGraph.jsx`: retained React Flow, persistent positions, primary analytical filters and exact delta emphasis.
- `frontend/src/DetectorPanel.jsx`: shared selected date; original anomaly scanning remains intact.
- `frontend/src/temporalModel.js`: explicitly identify human research context as context.
- `frontend/tests/workspace.test.js`: workspace/reducer/navigation, turn overlay, isolation, validation, persistence and component-wiring contracts.
- `src/financial_assistant/portfolio/__init__.py`, `returns.py`, `service.py`: pure deterministic analytics, cache adapter, compact reasoning context and graph projections.
- `scripts/anomaly_api.py`: three thin market/portfolio/simulation routes on the existing ThreadingHTTPServer.
- `scripts/investigation_api.py`: holding/relationship research entry points, server-calculated portfolio context and simulation provenance.
- `scripts/investigate_historical_pair.py`: optional neutral attention event and compact deterministic context before query expansion, hypothesis generation and audit.
- `scripts/missing_evidence_followup.py`: structured merge delta and completed reassessment IDs.
- `tests/test_portfolio_returns.py`: formulas, calendars, unavailable states, no-lookahead, graph lineage and holding entry point.
- `tests/test_missing_evidence_followup.py`: additional real two-turn merge/history test.
- This report.

## Application architecture and state

No router was installed: three routes and local workspace tabs are handled with History API pushState/popstate. Routes are `/portfolio`, `/explore`, and `/investigate/:workspaceId`. Unknown/stale routes restore Portfolio on initialization. Vite's existing SPA fallback serves these routes.

One explicit reducer owns portfolio, selected date, investigation workspace records, selected candidate, watched candidates and navigation. The shell supplies a React Context and passes explicit callbacks to the existing investigation component. There is no external state library. Browser storage key `claimgraph:workspace:v1` persists the portfolio and workspace graph/model snapshots. Graph data is referenced from each workspace for Portfolio research summaries, never copied into a separate news database. Portfolio and simulation requests use captured portfolio definitions, not whatever holdings happen to change later.

Each open investigation is a separately keyed, mounted component. Switching modes or tabs hides it without unmounting its graph. Selection, filters, temporal inspection, progress and review state therefore remain independent. Closing a tab removes only that workspace. Model/provider selection uses the existing configured-model endpoint; each tab prominently identifies its selected model. Running the same candidate in two tabs creates independent graphs and investigation IDs; outputs are never automatically merged. Recorded model-run provenance remains authoritative when the next-run selection changes.

Graph/model snapshots survive reload when local storage permits. Positions have a separate workspace-keyed storage record, and review storage is namespaced by investigation and workspace. Selection, filters and temporal inspection persist while mounted, but are not all restored after a full reload. Browser quotas can limit large replay persistence; existing JSON export remains available. Import/replay/export controls are retained under Investigation settings. Existing replay semantics and separate historical replay packets are preserved.

## Portfolio model and fixture

`{id, name, as_of, positions:[{ticker, weight}]}` is the explicit portfolio representation. Users edit ticker/decimal-weight lines and name; there is no trade history. Validate 1–100 unique securities, nonnegative finite weights, and a total within 0.001 of 1. Backend calculations explicitly normalize that small tolerance to exactly 1 and retain normalized weights in provenance.

The single fictional sample allocation is `DEMO_PORTFOLIO` in `workspaceStore.js`: **COHU 50%, PDFS 50%, as of 2026-03-20**. Both tickers exist in the supplied mapped US universe. These are fixture inputs, not a suggested allocation or invented performance. **This checkout contains no `data/cache/market/global_demo_daily.csv`; actual cache coverage and runtime market results could not be verified.** Populate the existing market cache using the project's existing workflow to run market demos. No replacement ingestion or fake live results were introduced.

Portfolio displays position count, editable holdings, returns, volatility, contributions, largest positive/negative contributors, largest weight and HHI concentration. Research status and unresolved questions come from relevant open/restored investigation graphs. Evidence is filtered to the Portfolio date using the existing temporal model. Latest research is a compact view of admitted claims/documents, not a generic news feed. No numeric investment risk score or quality ranking is generated. Refresh analysis is deterministic; the explicit Investigate action invokes existing BookReader/web/SEC research.

## Deterministic formulas and versioning

All calculations use **`market-performance-v1`**. Units are decimal ratios; the UI formats percentage metrics. No LLM calculates returns.

| Metric | Formula / policy |
| --- | --- |
| Security n-session return | `P[end] / P[end-n] - 1`, n = 1, 5, 20, 63, 252; require n+1 closes |
| Daily return | `P[t] / P[t-1] - 1` |
| Realised volatility | Sample standard deviation, `ddof=1`, times `sqrt(252)`; security windows 20 and 60 daily returns |
| Max drawdown | `min(wealth / running_max(wealth) - 1)`; include initial wealth of 1 |
| Portfolio daily return | `sum(normalized_weight[i] * return[i,t])` |
| Portfolio period return | `product(1 + portfolio_daily_return) - 1`; 1/5/20/63-session results |
| Holding contribution | `sum(prior_portfolio_wealth[t] * weight[i] * return[i,t])` over 20 aligned sessions |
| Concentration | Largest normalized weight and `sum(weight^2)` |
| Relative return | A's endpoint return minus B's, only with identical endpoint dates |
| Correlation | Pearson correlation of aligned portfolio and candidate daily returns; constant series are unavailable |

Linked holding contributions sum to the compound portfolio return for the same sample. They are contributions in percentage points of starting wealth, not attribution of economic causes. Portfolio risk/drawdown use the latest up to 252 aligned returns, with actual session count and dates exposed. Window start in summary denotes the first return's ending session; detailed price observations retain preceding input dates.

### Pair construction and overlay

The implementation deliberately uses the analytical **A-relative-to-B** scenario for all candidates: `q[t] = 0.5*rA[t] - 0.5*rB[t]`. A spread anomaly is not treated as sufficient authority for a trade direction. There is no automatic long/short recommendation. Identical/missing legs are unavailable.

Default gross overlay is 2%, user-adjustable from 0–100%. Combined daily return is `portfolio[t] + gross*q[t]`. This is a fixed daily-weight, zero-net-dollar analytical overlay added to unchanged base exposure. It assumes daily restoration of fixed weights, no financing, transaction costs, cash yield or slippage. There is no leverage or rebalance optimization. Lookback defaults to 252 sessions; the service permits 20–252 and returns shorter actual history only when at least 20 aligned sessions exist. Compare current portfolio, unit-gross candidate and combined returns, annualised volatility and drawdown on the **same** sample.

**Historical simulation is descriptive evidence about the selected historical sample. It is NOT an expected return forecast and NOT an investment recommendation.** Historical correlation or reduced volatility cannot establish future protection.

## Calendars, cutoffs and unavailable states

The service reuses the existing adjusted-close cache and its path identity. It does not download market data. Daily bars are conservatively available at UTC end of day (23:59:59.999999); intraday requests exclude that day's close. Date-only Portfolio/Explore requests mean end of that UTC date. Cutoff filtering occurs before all selection, arithmetic, input hashing and provenance construction. Tests alter every later price and confirm identical past returns, portfolio analysis, simulation and hashes.

Daily return intervals must have identical starting **and** ending observation dates across securities. No forward filling occurs. Keep the most recent contiguous common interval; reject a missing latest common return instead of silently using stale portfolio results. Gaps over four calendar days are treated as unavailable breaks, conservatively excluding unusually long market closures. This is a simple explicit calendar policy, not an exchange-calendar service. Annualisation assumes 252 sessions.

Missing/invalid securities, nonpositive/duplicate prices, incompatible calendars, insufficient history/overlap, invalid weights, undefined correlations and nonsimulatable candidates return explicit unavailable states/reasons. Security horizons can be independently unavailable. Stale UI calculation results are invalidated by portfolio/date/candidate/overlay changes. The existing anomaly fitter/scanner and held-out future-performance simulator are unchanged. Hindsight still executes only after reasoning and remains in its separately labeled layer.

## Research flows and provenance

**Portfolio → Investigation:** a holding opens a new workspace with portfolio/date context. An explicit run creates a `human_research_request` attention event, not a fabricated statistical anomaly. The same existing research pipeline receives server-calculated weight, returns and contributions as prioritisation context. It does not automatically admit that human context as Claim evidence or create causal support edges.

**Explore → Investigation:** selected scanned candidates use the existing live/historical selection validation. Their compact 1/5/20/63-session decomposition, relative returns and existing spread/z-score event context inform research without implying causes. Simulation is recalculated server-side at the investigation cutoff, rather than trusting browser-calculated results. A persistence/confounder Missing Evidence requirement links to generated hypotheses so human follow-up can reassess them.

**Investigation → Explore:** a pair workspace opens an overlay scenario at its original cutoff. Subsequent research can use a neutral relationship research request even when the original detector scan has expired; it does not invent a new anomaly. Holding-only investigations disable pair simulation until a pair exists.

Meaningful returns project as Calculation nodes, with `calculated_from` edges to deduplicated endpoint Price Observations containing ticker/date/field/value/source identity. Formulas, versions, cutoff and exact endpoint values are inspectable. Simulation retains the portfolio definition, normalized weights, construction, size, actual sample, complete cutoff price inputs and their SHA-256, version, assumptions and calculated outputs. Its compact price-series Observation feeds a Calculation; individual daily bars do not become thousands of visible nodes. Raw provenance can be revealed through filters/inspector. No inference that the scenario *will* diversify is created.

## Full-screen graph, inspector and second turn

React Flow remains the graph implementation. The canvas occupies the investigation viewport below the site/tab strips. Replay/model, review/Time Travel and filter controls are compact floating disclosures. Primary analytical types are visible by default; sources and execution nodes are subdued/filterable. Review summary remains accessible. Clicking a node/edge opens the right inspector drawer with existing source/model/SEC lineage, review and follow-up controls. Closing the drawer does not remount React Flow or reset positions. Progress collapses after execution.

Every new follow-up history item carries a `delta` derived from actual pre/post merge IDs:

- run, requirement, question and action IDs;
- added node and edge IDs;
- new supporting, weakening, contradicting and context relationship **edge** IDs;
- hypotheses whose bounded reassessment completed;
- previous/new resolution and remaining question.

The canonical graph is retained; there are no graph copies per turn. Existing history is append-only. A follow-up card displays actual counts by node/relationship type, question, searched task/tool records, inspectable new evidence, completed reassessments and old → new resolution. New nodes/edges are emphasized, earlier nodes subdued, and affected hypotheses outlined. **Show only new** filters to added nodes/edges; **Show in context** reveals affected hypotheses and relationship endpoints; **Inspect provenance** opens the action and its linked searches. Dismiss removes the overlay. A later completion selects the new delta. The turn selector reuses stored deltas, including an initial-node overlay when all follow-up deltas are available.

Old replay follow-ups without deltas are preserved but cannot reliably reconstruct an initial turn. Their action provenance is still inspectable. Empty or failed searches may leave the requirement unresolved; no successful resolution, causal relationship or new claim count is fabricated.

## Validation and limitations

Validation uses offline synthetic market inputs and existing saved graph fixtures; no live BookReader, web, SEC or configured-model acceptance run was performed. Frontend tests are focused reducer and source-wiring contracts, consistent with the existing Node test runner, not browser end-to-end interaction tests.

- `source .venv/bin/activate && python -m pytest -q`: **231 passed**.
- `npm --prefix frontend test`: 10 files passed.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed.
- `git diff --check`: passed.

The full backend suite requires execution outside the sandbox because the existing demo-runtime test opens local sockets. No commit or push was made.

Known limits: market cache is absent in this checkout; current sample coverage is not live-verified; historical adjusted-price revisions and survivorship are not reconstructed; no FX conversion (use a compatible-currency portfolio); no exchange calendar database; conservative four-day gap policy; browser storage quotas and partial reload restoration; no automated visual browser acceptance; initial overlays unavailable for legacy follow-ups lacking deltas; expired historical scanner IDs require a fresh scan for scanner-origin investigations. The command center summarizes loaded workspace research, not every replay on disk. No optimization, forecasts, expected-return estimates, automated recommendations, broker integration or post-hackathon infrastructure was implemented.

## DEMO A — PORTFOLIO COMMAND CENTER

1. Open Portfolio, review/edit the fictional sample weights and select a date covered by the existing cache.
2. Refresh analysis; inspect a meaningful positive/negative holding contribution and descriptive volatility/drawdown. Missing data displays its reason.
3. Review the holding's existing admitted documents/claims and unresolved research questions; if none are loaded, the page says no investigation exists.
4. Select the holding's Investigate action, choose a configured model and explicitly run research.
5. Click a Claim, return Calculation or Missing Evidence node; follow the inspector's provenance. Close the drawer to restore the full canvas.

Historical simulation is descriptive evidence about the selected historical sample. It is NOT an expected return forecast and NOT an investment recommendation.

## DEMO B — INVESTIGATION / SECOND TURN

1. In Explore, scan for an anomaly and open an investigation workspace. Select the model and run the initial ClaimGraph pipeline.
2. Select Missing Evidence and click **Investigate this question**.
3. When the bounded research finishes, inspect the question/searches and actual evidence counts in the follow-up result card.
4. Choose **Show only new** to identify exactly which nodes/relationships arrived. Choose **Show in context** to see the affected hypothesis highlighted.
5. Read the recorded old → new resolution. It can remain unresolved; a change is never manufactured.
6. Inspect the new evidence and execution provenance, then select earlier turns to compare their overlays over the current canonical graph.

Historical simulation is descriptive evidence about the selected historical sample. It is NOT an expected return forecast and NOT an investment recommendation.

## DEMO C — EXPLORE / PORTFOLIO RELEVANCE

1. Scan market anomalies, select a candidate and inspect its z-score, correlation, cointegration p-value, formation dates and recent relative-return decomposition.
2. Simulate against the current portfolio using the small default gross analytical overlay.
3. Inspect historical sample dates, candidate/portfolio correlation and the return/volatility/drawdown comparison. Open calculation provenance to inspect inputs and formulas.
4. Read the persistence/risk evidence requirement and select **Investigate persistence and confounders**.
5. Run the existing ClaimGraph research pipeline. Inspect whether admitted evidence supports, weakens, contradicts or merely contextualizes the economic rationale; use human-triggered follow-up for remaining questions.

Historical simulation is descriptive evidence about the selected historical sample. It is NOT an expected return forecast and NOT an investment recommendation.
