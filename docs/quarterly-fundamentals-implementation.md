# Quarterly SEC fundamentals MVP

The shared Live / Time Travel pair enrichment now calls `quarterly_metrics` for each security independently. It retains up to eight fiscal quarters and the existing three-year annual baseline. Annual formulas remain available for compatibility and secondary inspection, but the graph and reasoning instructions prioritize quarters. No provider infrastructure, network retry policy, dependencies, commits, or pushes were added.

## Files changed

- `src/financial_assistant/fundamentals/models.py`: typed snapshot records, bundle snapshots, calculation comparison period.
- `src/financial_assistant/fundamentals/normalize.py`: optional cumulative-context and eligible-version selection; small allowlist additions for reported diluted EPS, shares outstanding, investing cash flow and financing cash flow.
- `src/financial_assistant/fundamentals/quarterly.py`: fiscal grouping, quarter subtraction, deterministic metrics, comparisons, input retention and explicit unavailable results.
- `src/financial_assistant/fundamentals/service.py`: one retrieval per company, quarterly pair enrichment, annual compatibility, compact reasoning context, enriched observation metadata.
- `src/financial_assistant/claimgraph/schema_v2.py`: Context node kind. The active v2 schema previously had no Context node kind; this is a grouping category, not a new type of factual assertion.
- `src/financial_assistant/claimgraph/builder_v2.py`: company and quarter contexts, membership and trend links, descriptive hypothesis context links, JSON-stable missing-evidence warnings.
- `frontend/src/graphAdapter.js`: progressive quarterly graph projection and Context layout.
- `frontend/src/ClaimGraph.jsx`: collapsed SEC defaults, older-quarter control, quarter expansion, compact visible layout and retained dragging.
- `frontend/src/NodeInspector.jsx`: statement-section metric links, snapshot filing/cutoff information, calculation comparison/input fields, observation amendment/availability metadata.
- `frontend/src/temporalModel.js`: company Context visibility; snapshots still inherit the temporal eligibility of their constituent evidence.
- `tests/test_quarterly_fundamentals.py`: quarterly accounting and integration contracts.
- `frontend/tests/fundamentals.test.js`: collapsed/expanded graph, older quarters, preserved records and temporal eligibility.
- `docs/quarterly-fundamentals-implementation.md`: this report.

## Quarterly normalization

Raw facts remain immutable `FinancialFact` records. Context selection is by concept, exact start/end, newest eligible filing, then the existing alias priority. Ambiguous equally preferred contexts remain unavailable. The original annual and discrete-only normalizer behavior remains available; quarterly enrichment explicitly requests cumulative contexts too.

Contemporaneous eligible filing contexts establish fiscal starts and years. Quarter duration windows accommodate ordinary and 52/53-week calendars: 80–100 days, 170–195 days, 260–290 days and 350–380 days for cumulative Q1–Q4. Fiscal labels from much later comparative filings do not establish a fiscal year for an older fact. Eligible original versions can establish the calendar even when a later restatement supplies the selected value. A uniquely labeled standalone quarter can be grouped without inventing a missing fiscal-year start.

Instant concepts require no start date and remain point-in-time observations. Discrete flows must match the quarter's exact start and end. A directly reported quarter is preferred over subtraction. Otherwise additive flows require current and preceding cumulative contexts with the same fiscal start, taxonomy tag and unit; their end dates must establish the quarter boundary. Q4 can use FY minus nine months. Missing predecessors do not become zero. Weighted-average shares and EPS are never subtracted. Direct EPS is accepted only from the allowlisted diluted EPS tag with `USD/shares` units and an exact quarter context.

Only eight snapshots are public; transitive earlier observations/calculations needed for comparisons remain in provenance. Snapshots contain references to reported observations or derived calculations, never fabricated replacement observations. All inputs retained by annual baseline calculations are preserved too.

## Added deterministic formulas and versions

Every new calculation records its exact expression, input node IDs, flattened raw observation IDs, comparison end when relevant, unit, status, reason, and maximum input availability. Formula versions follow `<metric-id-with-hyphens>-quarterly-v1`.

| Metric family | Formula | Version examples / scope |
| --- | --- | --- |
| `<concept>_discrete` | current YTD minus preceding YTD | `operating-cash-flow-discrete-quarterly-v1`; additive duration concepts only, including capex and Q4 income flows |
| `total_debt` | short-term debt + current long-term debt + noncurrent long-term debt + current finance leases + noncurrent finance leases | `total-debt-quarterly-v1`; every component required, unless a directly reported total is available as an observation |
| `net_debt` | total debt minus cash | `net-debt-quarterly-v1` |
| `free_cash_flow` | operating cash flow minus capex | `free-cash-flow-quarterly-v1`; negative reported capex payments rejected |
| `gross_margin` | gross profit / revenue | `gross-margin-quarterly-v1` |
| `operating_margin` | operating income / revenue | `operating-margin-quarterly-v1` |
| `net_margin` | net income / revenue | `net-margin-quarterly-v1` |
| `free_cash_flow_margin` | free cash flow / revenue | `free-cash-flow-margin-quarterly-v1` |
| `<metric>_<qoq or yoy>_change` | current minus comparison | Applies to revenue, operating cash flow, capex, cash, net debt, shares outstanding and diluted weighted-average shares; e.g. `cash-qoq-change-quarterly-v1` |
| `<metric>_<qoq or yoy>_growth` | current / comparison minus 1 | Same seven metrics; e.g. `revenue-yoy-growth-quarterly-v1` |
| `<margin>_<qoq or yoy>_change` | (current margin minus comparison margin) × 10,000 | All four margin metrics; e.g. `operating-margin-yoy-change-quarterly-v1`; unit bps |

All ratio denominators must be positive; missing, zero or negative comparison denominators yield explicit unavailable results. Absolute changes can remain available when percentage growth is not meaningful. Comparisons require a unique preceding fiscal quarter or the same fiscal quarter in the preceding fiscal year, with elapsed-date checks; missing quarters are never bridged by comparing arbitrary adjacent rows. Quarterly returns are not annualized. Existing annual formulas and versions are unchanged.

## Snapshot, graph and inspector

A `context` node with subtype `fundamental_snapshot` records entity, fiscal year/quarter, start/end, investigation cutoff, maximum availability, metric references, unavailable metrics and all contributing filings. Filings are a list because a derived quarter may depend on multiple forms, accessions and filing dates; no single filing is falsely presented as its sole source.

A company fundamentals Context connects its snapshots to the investigation. Snapshot membership uses `derived_from` with an explicit grouping-only role. Quarter-to-trend and trend-to-hypothesis `context_for` edges are descriptive, not causal support. Observation-to-filing and calculation-to-observation/calculation edges are unchanged and fully retained in serialized replay.

The default frontend projection hides SEC atomic observations, filing/source nodes, annual calculations and intermediate calculations. It shows the latest four snapshots per company and a small selection of latest-quarter QoQ/YoY trends. The older-quarter control exposes retained snapshots. Clicking a quarter toggles its transitive evidence; the SEC atomic evidence control exposes all recorded accounting evidence. The inspector always receives the complete graph and links individual metrics through Income statement, Balance sheet and Cash flow sections. Snapshot and calculation source chains remain traversable even when their nodes are hidden on the canvas.

## Model context and research

The structured JSON contains separate company records, cutoff/status/warnings, eight bounded quarterly snapshots, latest-quarter deterministic comparison results, and explicitly secondary annual metrics. Snapshot metric rows have declared columns: metric, epistemic kind, provenance ID, value and unit. Each snapshot includes filing dates/accessions/forms and unavailable metric names. Trends include calculation IDs, comparison periods, availability, status and unavailable reasons. Full formulas and atomic input details remain in the graph/inspector; the model does not receive an unbounded XBRL dump.

The existing research query expansion and hypothesis-generation integration consumes this context before external research. Instructions request documentary explanations for revenue/margin changes, price versus volume, segment weakness, working capital, inventory, receivables/payables, restructuring and guidance. They prohibit inventing accounting facts or treating comparative weakness or cash-flow resilience as a proven cause. This change supplies context to existing model operations; it does not manufacture a model inference or automatically declare an evidence requirement satisfied.

## Availability, amendments and exclusions

Only permitted SEC forms filed by the investigation cutoff contribute. Company Facts dates remain conservatively available at the end of the full UTC filing day. Retrieval time is not publication time. Every cumulative input independently passes the cutoff, and calculations inherit the maximum availability of all inputs. A later amendment/restatement can change a later investigation but cannot alter the earlier selected state. IDs incorporate selected values/filings and calculation dependencies; replay uses persisted records without retrieval.

Amendment forms are explicitly flagged. Company Facts cannot reliably identify every restatement as such, so the inspector describes the latest eligible context and reports that limitation rather than claiming unverified restatement status. Existing SEC URLs and any available recent-submission metadata are retained.

The quarterly industrial model returns explicit unavailable status for companies identified by the existing financial-sector/SIC exclusion. Unmapped issuers, unsupported non-US facts, unsupported units and missing allowlisted concepts remain unavailable. No IFRS expansion or bank/insurance accounting was added. Existing SEC caching, rate limiting, bounded retries and retrieval failure handling are unchanged.

## Validation

- `source .venv/bin/activate; python -m pytest -q`: **188 passed** (6.68 seconds). The first sandboxed full run had 183 passes and one local-socket permission failure in the pre-existing demo-runtime test; an unrestricted rerun passed. Final rerun includes the additional edge-case tests.
- `npm --prefix frontend test`: passed, 7 test-file suites, including the added progressive-disclosure contract.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed.
- `git diff --check`: passed.

Tests cover correct quarterly grouping; point-in-time balances; direct income versus cumulative values; Q3 and Q4 subtraction; both source observations; QoQ/YoY fiscal relationships; margin denominators and basis points; post-cutoff mutation and amendment behavior; missing values and predecessors; both-company snapshots; compact model records; SEC graph lineage; offline serialization; non-calendar years; industry exclusions; progressive disclosure and frontend cutoff propagation. Existing tests were preserved. No live SEC request or manual browser acceptance session was required for these deterministic fixture-based checks.

## Known limitations

- Fiscal calendar recognition deliberately uses narrow duration windows and eligible contemporaneous metadata. Unusual transition years, very late filings without usable prior anchors, conflicting fiscal labels and custom taxonomy concepts may remain unavailable.
- Subtraction uses the latest eligible compatible contexts. Company Facts does not establish that differently filed comparative inputs have identical accounting-policy bases; semantic equality beyond the existing concept/unit/context checks is not asserted.
- Directly reported EPS and weighted shares remain available only for exact quarters. Weighted-average share-count change is distinguished from point-in-time shares outstanding; it is a dilution proxy, not proof of an issuance cause.
- There is no TTM, peer-difference attribution, segment normalization, accounting-quality score or long-term seasonality model. Multi-quarter paths are inspectable in snapshots; no separate four-quarter direction classifier was added.
- The existing annual API defaults remain for backward compatibility. The shared investigation pipeline and explicit quarterly service calls use the new engine. Annual-only evidence is labeled secondary and does not masquerade as a quarterly snapshot.
- This MVP expands a quarter's constituent evidence on the canvas; statement sections are organized in the inspector rather than introducing additional graph primitives.

SEC filing → atomic observation → quarterly snapshot → deterministic calculation/trend → model inference → evidence requirement / claim / hypothesis.

Filing selection, observation normalization, snapshot grouping, arithmetic and provenance links are deterministic application operations. Interpretations, research requirements and explanatory claims/hypotheses are model-generated through the existing reasoning pipeline and require documentary evidence; accounting trends alone do not establish causation.
