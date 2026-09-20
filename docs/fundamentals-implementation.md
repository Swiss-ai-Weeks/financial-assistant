# Point-in-time fundamentals implementation report

ClaimGraph now enriches both legs of live and historical anomaly investigations with SEC Company Facts before research query expansion and hypothesis generation. The default pack uses three annual periods; the service supports one to five annual or clearly identifiable standalone quarterly periods. Existing Observation, Calculation, Document, Source and Missing Evidence node semantics are retained. No commit or push was performed.

## Runtime configuration

Set `SEC_USER_AGENT` on the backend to an application name and your contact email or URL. There is no API key and no browser SEC request. Without this setting, the news pipeline continues and each company gets an explicit fundamentals-unavailable result and Missing Evidence node.

`SECProvider` uses official ticker mapping, Company Facts and submissions endpoints. Requests share a process-wide 250 ms start interval (at most four per second). Socket timeouts default to 10 seconds and are capped at 20 seconds; streamed response reads also check a deadline. At most two retries are allowed, with bounded backoff; 403 and other non-retryable HTTP errors stop immediately. Payloads are capped at 40 MiB. Deployments with multiple independent backend processes would need a shared rate budget before scaling requests.

The server cache is `.run/fundamentals/`, with versioned CIK-specific entries containing retrieval timestamp, raw response and SHA-256. TTL is 24 hours. Cache updates are atomic. Cached data ALWAYS passes through cutoff selection again. No raw Company Facts payload or User-Agent is exposed in browser/replay results.

References consulted: [official SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), and [SEC filing taxonomy definitions for debt including capital leases](https://www.sec.gov/Archives/edgar/data/789460/000104746914000906/R46.htm).

## Historical availability and normalization

- Only 10-K, 10-K/A, 10-Q and 10-Q/A facts are accepted.
- Filing availability, never period end or retrieval time, controls inclusion. Company Facts has date-only filing metadata, so the entire UTC filing day must have elapsed. This conservative rule can omit facts already available earlier that same day. Submissions acceptance metadata is retained when available but does not relax this boundary.
- Cutoff filtering happens before choosing a submission. Newest eligible filing wins, then the explicit ordered alias preference within that filing date. Conflicting values, starts or accessions within that selection are unavailable. Later restatements/amendments cannot leak into an earlier cutoff.
- Facts retain ticker, CIK, issuer, taxonomy/tag, value/unit, duration start or instant context, period end, supplied fiscal year/period, form, filed date, conservative availability timestamp, accession, frame, provider and retrieval timestamp. Supplied fiscal year can describe the reporting filing, so graph labels use period-end dates instead of relabeling comparative periods with that year.
- Annual durations must be 350–380 days; standalone quarters 80–100 days. YTD cash flow and income values are excluded from quarters. No quarter subtraction/annualization is implemented. Instant balances must match the relevant duration end; opening balance calculations require the exact day before the duration start.
- Only USD monetary values and shares for weighted-average share counts are admitted. No currency translation, custom taxonomy interpretation or silent fallback to incompatible units.
- Duration inputs within a calculation must have identical start/end contexts. YoY requires one prior comparable period 350–380 days earlier with duration length within seven days.

## Metric definitions

All formulas are application code in `fundamentals/metrics.py`. Every result stores a deterministic ID, display name, version, formula, required inputs, period/frequency, value/unit, direct component IDs, transitive fact IDs, availability, status, warnings and assumptions. Unsupported denominators and missing inputs produce structured unavailable results independently of other metrics. Each metric version is its hyphenated ID plus `-v1`; ROIC is explicitly `roic-v1`.

| Public metric | Formula | Unit | Default pack |
| --- | --- | --- | --- |
| `revenue_growth_yoy` | revenue / prior comparable revenue - 1 | ratio | yes |
| `operating_margin` | operating_income / revenue | ratio | yes |
| `free_cash_flow` | operating_cash_flow - capex_outflow | USD | yes |
| `free_cash_flow_margin` | free_cash_flow / revenue | ratio | yes |
| `cash_conversion_or_cfo_to_net_income` | operating_cash_flow / net_income | ratio | yes |
| `net_debt` | total_debt - cash | USD | yes |
| `net_debt_to_ebitda` | net_debt / derived_ebitda | multiple | yes |
| `interest_coverage` | operating_income / interest_expense | multiple | yes |
| `capex_to_revenue` | capex_outflow / revenue | ratio | yes |
| `asset_turnover` | revenue / average_assets | multiple | yes |
| `roic` | NOPAT / average(beginning, ending invested capital); invested capital = equity + debt - cash | ratio | yes |
| `share_dilution_yoy` | diluted_shares / prior comparable diluted_shares - 1 | ratio | yes |
| `net_margin` | net_income / revenue | ratio | generic interface |
| `operating_cash_flow_margin` | operating_cash_flow / revenue | ratio | generic interface |
| `working_capital_to_revenue` | working_capital / revenue | ratio | generic interface |

ROIC-v1 uses reported tax expense / positive pretax income, only if the rate is within [0, 1]. NOPAT is operating income × (1 − that rate). Invested capital is equity + debt − cash. The denominator is the average exact opening and closing invested capital and must be positive. No normalized tax assumption is invented.

The debt definition includes capital/finance leases. Direct `DebtAndCapitalLeaseObligations` is preferred. Otherwise ALL of short-term borrowings, current maturities of long-term debt, noncurrent long-term debt, current finance leases and noncurrent finance leases must be reported (including explicit zeros). These are exposed as an intermediate total-debt calculation. The constructed definition excludes operating leases. Warnings propagate to dependent metrics. Missing debt or lease balances are never zero-filled.

Capex is a positive reported payments amount. Negative payments are treated as ambiguous/unavailable rather than silently inverted. FCF subtracts the normalized positive outflow. Operating income is the stated EBIT proxy. Derived EBITDA is operating income + reported D&A (which may include depletion), never company-reported EBITDA. Quarterly net debt / EBITDA is unavailable; other quarterly flow ratios/returns explicitly remain unannualized.

Intermediate calculations are capex outflow, total debt, derived EBITDA, working capital, average assets, effective tax rate, NOPAT, invested capital and average invested capital. ROIC traverses to NOPAT/tax-rate and average-invested-capital calculations, then filing observations and SEC source documents. Generic calculation dependencies reject missing IDs and cycles.

Descriptive endpoint trends use at least three contiguous annual values: margins/ROIC in basis points, and net-debt percentage change only with a positive initial balance and nonnegative final balance. Trends have their own version, IDs and endpoint lineage. They never assert causality.

## Explicit canonical US-GAAP mapping

Ordered aliases are separated by arrows. No additional tags are guessed outside this registry.

| Canonical concept | US-GAAP tag(s) |
| --- | --- |
| `revenue` | `RevenueFromContractWithCustomerExcludingAssessedTax` → `Revenues` → `SalesRevenueNet` |
| `gross_profit` | `GrossProfit` |
| `operating_income` | `OperatingIncomeLoss` |
| `pretax_income` | `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` → `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments` |
| `tax_expense` | `IncomeTaxExpenseBenefit` |
| `net_income` | `NetIncomeLoss` |
| `interest_expense` | `InterestExpense` |
| `cash` | `CashAndCashEquivalentsAtCarryingValue` |
| `accounts_receivable` | `AccountsReceivableNetCurrent` |
| `inventory` | `InventoryNet` |
| `current_assets` | `AssetsCurrent` |
| `total_assets` | `Assets` |
| `accounts_payable` | `AccountsPayableCurrent` |
| `current_liabilities` | `LiabilitiesCurrent` |
| `short_term_debt` | `ShortTermBorrowings` |
| `current_long_term_debt` | `LongTermDebtCurrent` |
| `long_term_debt` | `LongTermDebtNoncurrent` |
| `total_debt` | `DebtAndCapitalLeaseObligations` |
| `finance_lease_current` | `FinanceLeaseLiabilityCurrent` |
| `finance_lease_noncurrent` | `FinanceLeaseLiabilityNoncurrent` |
| `shareholders_equity` | `StockholdersEquity` |
| `operating_cash_flow` | `NetCashProvidedByUsedInOperatingActivities` |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment` |
| `depreciation_and_amortization` | `DepreciationDepletionAndAmortization` |
| `diluted_shares` | `WeightedAverageNumberOfDilutedSharesOutstanding` |
| `basic_shares` | `WeightedAverageNumberOfSharesOutstandingBasic` |

## Integration, graph size and replay

The real shared `investigate_signal` path handles both LIVE and TIME TRAVEL. It obtains both companies at `observed_at`, supplies compact ID-referenced financial context to query expansion, hypotheses and hypothesis audit, then builds the existing InvestigationState/ClaimGraph. No autonomous retrieval loop was added. The retrieval budget is unchanged.

Only selected high-value observations (revenue, operating income, net income, CFO and cash), inputs to available calculations, exposed metric calculations and their required intermediates are graphed. Unavailable calculations stay in the typed bundle, not as fake observations or zero values. A few key metrics and trend nodes link to hypotheses with `context_for`, explicitly without causal support. SEC filings use public filing-index URLs and metadata; full filing text is not claimed to have been fetched or extracted.

The typed graph includes the compact normalized bundles. Existing API replay and historical CLI graph persistence therefore save exactly the observations and available calculations shown, plus unavailable statuses and execution metadata. Loading saved JSON does not call SEC. No change to `scripts/investigation_api.py` was needed because it already serializes the graph.

Progress monitoring was detected and reused, including its existing callback and safe counter allowlist. Added stages report loading fundamentals, calculating metrics and completion; counts are `fundamental_facts_selected` and `fundamental_metrics_calculated`. Deterministic execution metadata stays distinct from ModelRun provenance.

NodeInspector shows metric/value, period end, formula/version, filing/availability, warnings/assumptions and execution. Existing relationship navigation follows intermediate calculations and sources. SEC source links work even while BookReader source-link configuration is unavailable.

## Accounting and coverage limits

This is a conservative MVP, not an institutional accounting-normalization engine. ROIC-v1 is one explicit definition. There is no causal inference merely from deterioration. Current ticker mappings, SEC source quality, surviving issuers and later collection of historical filings can still introduce coverage/data-quality limitations; this is not a claim of complete survivorship-free historical coverage.

Current existing universe sector metadata, with SEC SIC 6000–6499 as fallback, suppresses industrial ROIC, EBITDA leverage, interest coverage and related intermediate metrics for financial institutions (banks, insurers and other financial businesses). Results say `not_applicable` with a reason. Classification is explicitly current metadata used to suppress metrics, not an assertion of historical sector membership. Unknown classifications can remain incomplete.

Other limits: issuer-wide standard-tag facts only; no segment reconciliation, custom extensions, currency conversion, discontinued-operation reconciliation, acquisition/pro-forma adjustment, earnings normalization or restatement reconstruction beyond the eligible facts SEC retains. Explicit finance lease balances and D&A are often missing, reducing leverage/ROIC coverage rather than prompting guesses. Fiscal stub periods, ambiguous contexts, some old submissions metadata and YTD-only quarters are omitted. The service does not reconcile every accounting line to complete statements or normalize cross-issuer presentation differences.

Non-US support still needs another FundamentalsProvider, appropriate filing-availability provenance, IFRS/local taxonomy mappings, currencies/units and jurisdiction-specific fixtures. Foreign SEC forms and commercial providers were not added.

No live Company Facts, submissions or ticker API call was performed. SEC documentation and filing taxonomy pages were consulted through web search; all implementation tests use synthetic, realistic local fixtures or fake transports.

## Validation and exact files

- `source .venv/bin/activate && python -m pytest -q`: **179 passed** in 6.40 seconds, including **62 new fundamentals/SEC tests**. The existing demo-runtime socket test required running outside the filesystem/network sandbox; no test contacted SEC.
- `npm --prefix frontend test`: **7 test files passed**, zero failures; the new file adds three financial lineage/temporal/source-link checks.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed, 183 modules transformed.
- `git diff --check`: passed.

The worktree was initially clean on `feature/true-time-travel` at `e4b4ec0`, with one worktree at `/home/codexdev/projects/claimgraph`. Existing progress-monitor code was present and extended rather than overwritten. Changes remain uncommitted.

Exact changed/added files:

- `docs/fundamentals-implementation.md`
- `frontend/src/NodeInspector.jsx`
- `frontend/tests/fundamentals.test.js`
- `scripts/investigate_historical_pair.py`
- `scripts/investigation_progress.py`
- `src/financial_assistant/claimgraph/builder_v2.py`
- `src/financial_assistant/claimgraph/schema_v2.py`
- `src/financial_assistant/domain.py`
- `src/financial_assistant/fundamentals/__init__.py`
- `src/financial_assistant/fundamentals/metrics.py`
- `src/financial_assistant/fundamentals/models.py`
- `src/financial_assistant/fundamentals/normalize.py`
- `src/financial_assistant/fundamentals/provider.py`
- `src/financial_assistant/fundamentals/sec.py`
- `src/financial_assistant/fundamentals/service.py`
- `src/financial_assistant/llm/hypothesis_audit.py`
- `src/financial_assistant/llm/hypothesis_generation.py`
- `src/financial_assistant/retrieval/query_expansion.py`
- `tests/fixtures/fundamentals/companyfacts.json`
- `tests/fixtures/fundamentals/submissions.json`
- `tests/test_fundamentals.py`
- `tests/test_hypothesis_audit.py`
- `tests/test_investigation_api.py`
- `tests/test_sec_provider.py`
