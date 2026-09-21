# Missing Evidence follow-up — Geneva MVP

Implementation update: [Heterogeneous evidence assessment](heterogeneous-evidence-assessment.md) supersedes this report’s original claim-only reassessment limitation. The same bounded follow-up now assesses newly added SEC observations/calculations alongside claims, and new graphs no longer automatically classify financial metrics as context. The original loop and its safeguards remain in place.

A human can select a Missing Evidence or Evidence Requirement node and click **Investigate this question**. This runs one synchronous bounded cycle through the existing HTTP server. The graph remains mounted and usable. There is no queue, autonomous recursion, graph database, or additional service. A process-wide nonblocking lock permits one follow-up at a time; another request receives an error.

## Exact files changed

- `scripts/missing_evidence_followup.py`: bounded planning, dated peer selection, existing retrieval/SEC integration, resolution, targeted reassessment, incremental merge, execution records.
- `scripts/investigation_api.py`: explicit follow-up entry point, configured model selection, lock, progress, atomic replay save.
- `scripts/anomaly_api.py`: `POST /api/investigations/followup` route.
- `scripts/investigation_progress.py`: allowlisted follow-up/resolution stages and completion tracking.
- `src/financial_assistant/claimgraph/schema_v2.py`: execution node/edge kinds and follow-up history field.
- `frontend/src/App.jsx`: human callback, existing progress monitor, graph update with stable workspace identity.
- `frontend/src/ClaimGraph.jsx`: merge rendered nodes while retaining stored positions and local filter state.
- `frontend/src/NodeInspector.jsx`: action, resolution, evidence/counterpoint links, remaining question, history and counts.
- `frontend/src/InvestigationProgress.jsx`: display inherited cutoff for follow-ups.
- `frontend/src/investigationClient.js`: follow-up endpoint, state transition, real execution stages.
- `frontend/src/temporalModel.js`: distinguish execution context from dated evidence.
- `tests/test_missing_evidence_followup.py`: backend cycle, source, failure, targeting, temporal, provenance and replay tests.
- `frontend/tests/followup.test.js`: request/reducer, progress, inspector wiring, temporal execution context and export contracts.
- `docs/missing-evidence-followup.md`: this report.

## Data model and epistemic semantics

Existing Observation, Calculation, Context, Inference, Claim, Hypothesis, Missing Evidence, Evidence Requirement, Source, Document and Model Run concepts remain distinct. Three execution kinds are added: `agent_action`, `research_task`, `tool_call`. Added edges are `investigates`, `generated_task`, `retrieved`, `resolves`, and `partially_resolves`.

Each human execution has a stable run ID. The original requirement remains, with `resolution_status`, `resolution`, and append-only `followup_history` action IDs. The graph's `followups` list records run ID, requirement ID, inherited cutoff, resolution and action ID. Each action holds the human trigger, provider/model, dated peer-selection result, SEC availability, counts, and sanitized failures.

Resolution contains requirement ID, `answered | partially_answered | unresolved`, summary, supporting/contradicting **graph node IDs**, remaining question, and resolution model-run ID. Resolution validation rejects references outside the actual new evidence set and rejects non-unresolved outcomes without citations. No new grounded evidence yields unresolved without a model call. Model judgments remain inspectable judgments, not guarantees of truth. A supported negative answer may answer a question; inconclusive counter-evidence leaves it partially answered or unresolved.

Observations record source values. Calculations retain deterministic SEC formulas and lineage. Documentary claims retain validated source quotations and extraction runs. Sector behavior is context; peer analogy cannot establish a causal mechanism. The existing relationship assessor distinguishes support, contradiction, weakening, context, and unrelated results, explicitly warning against causal inference from financial results alone. The cycle does not invent an inference or causal claim merely to populate a visual chain.

## Planning and peer selection

Four deterministic ResearchTasks address company-specific evidence, peer comparison, sector context, and contradiction/alternatives. Inputs include the selected question, original anomaly/tickers/cutoff, affected parents and connected evidence, compact quarterly financial context, and deterministic peer identity. Existing issuer aliases are reused. Query expansion can broaden beyond the original tickers, but its output is explicitly labeled research hypotheses, not evidence.

Each task retains at most three expanded queries; the existing retrieval service additionally bounds executed concepts by a two-hit per-task budget. At most six dated documents reach extraction, two claims per document, twelve claims overall. An expansion error falls back to a bounded deterministic question query. No new gap starts another cycle.

Peer selection sorts ticker IDs and takes at most three mapped securities, excluding the original entities. It requires the same universe, currency and sector, plus industry/subindustry when supplied. Membership/classification must have `valid_from <= cutoff` and an absent or later `valid_to`. These are date-granularity identity intervals, not financial evidence.

**Current data limitation:** `global_equities.csv` has no validity dates. Consequently the current demo conservatively reports historical peer/sector identity unavailable and selects no historical peers. It does not backfill today's classification into Time Travel. The deterministic selection path is tested with dated metadata. Supplying point-in-time identity metadata is necessary to enable historical peer retrieval with this dataset. Broad sector searches may still generate research hypotheses, which require dated documentary evidence.

## SEC, BookReader and web

The cycle calls the existing `load_pair`, `model_context`, and `domain_evidence` functions for target, comparison and eligible peers. It reuses quarterly snapshots, deterministic trends, missing-value records, source IDs, and existing financial-industry exclusions. Raw XBRL observations are not sent to the follow-up model context. SEC observations/calculations retain their normal graph lineage; SEC tool-call records also retain availability and execution timestamps.

BookReader corpus search and SearXNG web discovery use the existing composite search and dispatching fetcher. Lightweight wrappers isolate provider configuration/search failures and record fixed failure messages. Successful providers can continue when another fails. Retrieval records retain task, query, provider, timestamp and status; transport exception bodies are omitted. Search hits and excluded documents remain execution metadata, not evidence nodes. Documents enter the graph without article bodies. Grounded claim extraction uses the existing quote-validation implementation.

## Targeted reassessment and merge

The affected set is the requirement's incoming `requires` parents and explicit hypothesis ID; requirements on claims may include hypotheses directly related to that claim. Each affected hypothesis is assessed separately against the new grounded claims. Other hypotheses are never regenerated or assessed. SEC calculations receive the existing descriptive `context_for` relationships, not invented causal support.

A delta graph is built using the existing typed builder. Original nodes are retained by ID; new nodes and previously unseen edges are appended. Only the selected requirement's resolution metadata changes. Relationship assessment IDs include the follow-up run ID, so earlier assessments remain historical execution records. Additional unresolved questions become Missing Evidence nodes requiring a new human action. Original fundamentals/model/source records remain intact.

The client replaces the graph value only after a complete response, keeping the same workspace key. Existing review decisions, selection, temporal cutoff, filters and stored graph positions survive. The selected inspector item is refreshed by ID. New nodes are added to ReactFlow's rendered layout. New positions use the existing layout algorithm and may require manual repositioning in dense graphs.

## Time Travel and provenance

The cutoff comes from the original anomaly's observed timestamp (or detected timestamp), never the browser's currently inspected date or execution time. Every research plan, search and SEC request inherits that cutoff. The existing strict document selector requires known publication time; date-only publications on the cutoff date are admitted only at the complete end of that day. Unknown/future documents cannot enter extraction or evidence nodes.

SEC normalization continues to exclude filings, amendments and restatements unavailable at the cutoff. Existing tests cover those rules. Retrieval time is execution provenance and never grants historical admissibility. Dated peer identity is subject to its own eligibility gate. Execution nodes can be inspected at the original cutoff because they describe today's reconstruction, not facts known then.

Action, task, query-expansion model records, provider search attempts, retrieval records, SEC calls, extraction runs, resolution run and relationship runs expose what happened. Epistemic edges/quotes/formulas expose why an item bears on the question. Progress uses the existing polling registry and an allowlist of stages/counts; it never accepts prompts, document bodies, tokens or exception text. There are no estimated percentages.

## Failure behavior and persistence

- Empty or useless retrieval: unresolved.
- SEC unavailable: reason retained; documentary retrieval continues.
- BookReader/web unavailable: per-provider failure retained; other providers continue.
- Query expansion fails: recorded failure and deterministic fallback.
- Extraction fails: recorded per-document failure; no fabricated claim.
- Resolution fails or supplies invalid evidence IDs: unresolved, failure recorded.
- Relationship reassessment fails: original assessment remains; action exposes failure for that hypothesis.
- Unexpected whole-cycle failure: progress fails, lock releases, original client graph remains.

Successful follow-ups atomically save a new replay packet, preserving the prior packet and graph history. Browser export includes the merged graph, follow-up records, and existing review. The request carries the existing graph, consistent with the local prototype; this is not an authenticated multi-user persistence API. In-flight jobs do not survive server restarts.

## Validation

The follow-up tests cover explicit API execution, singleton lock, original cutoff, four-task bound, contradiction search, deterministic dated peer/currency/industry constraints, all three evidence sources, future document exclusion, resolution states and citation validation, no recursion, graph/node/provenance preservation, targeted and failed reassessment, sanitized progress/failures, and replay round-trips. Existing SEC tests cover future filings/restatements and financial-industry exclusions. Frontend contract tests cover keeping the graph on start/failure, stable workspace identity on success, explicit action wiring, follow-up progress, and export retention. These are component wiring/state contracts, not automated browser end-to-end tests or live-provider acceptance tests.

Validation results:

- `source .venv/bin/activate && python -m pytest -q`: 200 passed. The first sandboxed run could not create sockets for the existing demo-runtime test; the full suite passed with approved execution outside that restriction.
- `npm --prefix frontend test`: 8 test files passed.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed.
- `git diff --check`: passed.

No commit or push was made.

## Remaining limitations

No autonomous research, peer engine, peer median/range feature, new bank metrics, graph-wide propagation, task queue or production permissions were added. The original financial implementation excludes generic quarterly industrial metrics for banks; deposit costs, net interest margin and loan growth are not newly implemented. Resolution is model-assessed with structural grounding checks, not deterministic semantic proof. No live BookReader/SEC/web/model acceptance run is claimed. Peer comparisons require dated identity metadata, absent from the supplied universe file.

## Worked example: SHBI / THFF

This is a conditional walkthrough, not fabricated retrieval output or a claim that a live run found these facts.

**Question / Missing Evidence:** “What sector-specific factors have recently impacted either SHBI or THFF disproportionately?” The original question remains attached to its hypothesis, H3.

**Research tasks:** (1) seek company-specific disclosures about differential exposure; (2) compare against eligible peers and actively look for normal exposure; (3) retrieve dated sector context, potentially expanding into deposit competition, funding costs or interest rates; (4) search for contradiction and alternative explanations. These tasks and expansions are execution provenance and research hypotheses, not evidence.

**Peer set:** With the current undated universe CSV, the historical peer set is empty and the reason is visible. With supplied dated metadata, up to three same-universe/currency/sector peers could be selected deterministically. Their identities alone are context, not proof of shared behavior.

**SEC calculations:** Request the inherited-cutoff quarterly fundamentals for SHBI/THFF and any eligible peers. Current bank exclusions yield unavailable generic quarterly calculations. Therefore this demo must not display an invented SHBI deposit-cost observation, peer median calculation or excess-deterioration comparison. Those would require supported bank metrics and actual eligible filings.

**BookReader/web evidence:** If dated sources explicitly report sector deposit competition, their grounded quotations may yield a claim that the sector experienced competition. If a separate eligible source reports SHBI-specific pressure, extract that as its own claim and retain its document/source/model links. An observation in a source and a source-grounded claim about it remain distinguishable from an application-calculated metric.

**Grounded claims and context/analogy:** Sector competition may provide context for H3. Comparing it with SHBI is an analogy unless supported by direct company evidence. An inference that SHBI was unusually exposed requires an actual comparative evidential basis; the pipeline must not manufacture it from peer membership.

**Contradiction/counterpoint:** If eligible evidence indicates THFF or other banks experienced similar pressure, retain it. It may weaken the disproportionate-exposure hypothesis or merely supply context; the targeted assessor records which and why.

**Resolution state:** Sector-only evidence cannot answer the disproportionate-impact question. A model may mark it partially answered with cited new claims and an explicit remaining gap, or unresolved if no relevant new evidence exists. Answered is permitted only when cited evidence addresses the original question, including a well-supported finding that exposure was not disproportionate.

**Affected hypothesis reassessment:** Assess new grounded claims against H3 only. Preserve earlier H3 assessments and all H1/H2/H4 nodes, relationships and human review decisions. Add execution links to the follow-up action and model runs.

**Remaining Missing Evidence:** “Was any excess pressure driven by deposit mix, geography, pricing decisions, or another factor?” is recorded only if the resolution assessment actually returns it. It is not automatically researched. The human may inspect the claims, sources, calculations (if available), contextual/contradictory relationships and execution provenance, then explicitly start another bounded cycle.
