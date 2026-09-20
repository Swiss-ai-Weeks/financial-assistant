# Heterogeneous analytical evidence assessment

## Root cause

The domain and graph builder already supported typed relationship sources, but `assess_relationships(claims, hypotheses, provider)` only serialized ExtractedClaim objects and hard-coded `source_kind=CLAIM`. SEC observations/calculations could not reach that model call. Initial investigations and Missing Evidence follow-ups inherited this restriction. Separately, the builder automatically attached selected financial metrics to every hypothesis with `context_for`, without an actual relationship judgment.

The shared assessor now accepts native analytical objects and preserves their kinds and IDs. New graph construction no longer invents automatic financial `context_for` classifications. Existing saved graphs and previous follow-up relationships remain untouched. Nothing requires diverse relation counts or relaxes the causal standard.

## Exact files changed in this task

This task continued the preceding uncommitted working tree. It did not discard or independently recreate the follow-up feature.

- `src/financial_assistant/llm/evidence_arguments.py`: typed adapter, deterministic bounded selection, diagnostic aggregation/logging.
- `src/financial_assistant/llm/relation_assessment.py`: shared heterogeneous API, prompt v2, typed pair validation, execution-specific assessment IDs.
- `src/financial_assistant/claimgraph/builder_v2.py`: remove automatic metric context edges; retain all judgments and diagnostics on assessment ModelRun nodes.
- `scripts/investigate_historical_pair.py`: supply existing financial observations/calculations to initial relationship assessment.
- `scripts/missing_evidence_followup.py`: supply newly added observations/calculations to the same assessor; retain targeted scope and action-level diagnostics.
- `frontend/src/reviewModel.js`: add explicit context role/count, preserving existing heterogeneous support/counter counting.
- `frontend/src/NodeInspector.jsx`: explicit typed source, target hypothesis and assessment details on epistemic edges.
- `tests/test_heterogeneous_assessment.py`: typed assessor, bounding, semantics, builder/provenance, actual SEC formula lineage and follow-up contracts.
- `tests/test_fundamentals.py`: strengthen initial pipeline integration test; replace its obsolete expectation of an unassessed automatic context edge.
- `frontend/tests/heterogeneousAssessment.test.js`: native-kind counts, excluded execution edges, traversal and inspector wiring.
- `docs/missing-evidence-followup.md`: note that this extension supersedes the original claim-only reassessment limitation.
- `docs/heterogeneous-evidence-assessment.md`: this report.

## API and internal representation

The existing call remains valid:

```python
assess_relationships(claims, hypotheses, provider)
```

The shared extended call is:

```python
assess_relationships(
    claims, hypotheses, provider,
    observations=observations,
    calculations=calculations,
    inferences=inferences,
    max_arguments=16,
    max_workers=4,
)
```

The first collection can also contain a mixture of native domain objects or internal EvidenceArguments. There is no conversion into fake ExtractedClaims.

`EvidenceArgument` contains `source_kind`, `source_id`, readable `text`, `provenance_summary`, and internal selection metadata. Claim arguments retain claim type, exact source quotation, document ID and extraction run. Observation arguments retain value/unit and source document. Calculation arguments retain deterministic formula, input observation/calculation IDs, units, period/comparison period, metric and availability metadata where present. Inference arguments explicitly say model-derived, NOT a direct observation, and retain input IDs/model run.

The response contract uses `source_kind`, `source_id`, and `hypothesis_id`. Exact typed pairs are validated for completeness, unexpected identities and duplicates. Legacy claim-only `claim_id` responses remain accepted for compatibility; they cannot masquerade as calculations because their default kind is Claim and validation must match the supplied typed identity.

## Evidence bounding

The default is at most 16 arguments per hypothesis; callers may request 1–20. Inputs come from the existing admitted documents and deterministic financial projection, not another retrieval stack.

Selection is deterministic. Initial budgets are six grounded claims, six calculations, two observations and two inferences. Within kinds, term overlap with the hypothesis ranks relevance, then period recency and quarterly/trend metadata break ties. Calculation inputs are deprioritized when selecting observations, so independent important values are preferred. Unused capacity is filled from the remaining ranked inputs. Opaque IDs are never rewritten. Selection ranks are not confidence or relationship scores.

This is a lightweight lexical selection policy. It does not guarantee that every materially relevant argument fits the budget, and it does not treat dependent observations/calculations as independent corroboration. The compact fields reuse the existing quarterly calculation metadata; neither complete raw XBRL objects nor all SEC nodes are dumped into the model. No embeddings, reranker, new provider, or peer-selection engine was added.

## Prompt and semantics

Prompt version is `relation-assessment-v2`.

The prompt asks the model to consider an increase in plausibility, a decrease, direct conflict with a necessary premise, or nondiscriminating context before assigning a relation. Supports means increasing plausibility of the EXACT supplied hypothesis, not proving the entire causal story. Weakens and contradicts remain distinct. Relevant but nondiscriminating evidence remains context; unrelated remains available.

The same measured deterioration can support “unusually severe relative margin pressure” and provide only context for “margin pressure caused the stock-price divergence.” Investor reaction, timing and expectations remain missing evidence unless observed. Assumptions and missing_information remain required response fields/defaults and are preserved on graph judgments.

Claims may themselves be forecasts or interpretations. Inferences are explicitly identified as analytically/model-derived and do not become observations. Peer comparisons alone do not prove target causality. Research intent does not assign the relation: a document discovered by the existing contradiction task can receive any justified label. The four original research tasks are unchanged; there is no second challenge-search system.

## Initial and follow-up integration

The normal initial pipeline now passes `financial_observations` and `financial_calculations`, produced by the existing `domain_evidence` projection, alongside grounded documentary claims. The shared assessor chooses its bounded set separately for each hypothesis. Quarterly trends enter as real Calculation IDs, with their existing lineage. Important observations enter as real Observation IDs. Explicit Inference objects are supported by the same API; the current initial/follow-up pipelines do not generate a separate new inference collection, and this task does not invent one.

The existing Missing Evidence cycle filters candidate claims, observations and calculations against original graph IDs. It passes only newly added items to the shared assessor, even when there are no new documentary claims. It still calls only affected hypotheses, one at a time, preserving per-hypothesis failure isolation. Re-fetching an identical already-recorded SEC node does not make it new evidence. The existing graph merge, four tasks, human trigger, progress, retrieval, resolution and replay paths remain in place.

Resolution semantics and citation validation are unchanged. Relationship counts cannot mark a requirement answered. A follow-up can produce support and remain partially answered; it can produce a supported negative answer; it can remain unresolved. The new test explicitly verifies that calculation reassessment alone does not manufacture a resolution result.

## Graph, review and execution provenance

Only actual RelationshipAssessments create new financial epistemic edges. The builder's old automatic financial context edges were removed, rather than competing with a model's supports/weakens/contradicts/unrelated judgment. Previously saved edges are retained by the incremental merge.

Native graph traversal remains:

- Calculation → `calculated_from` → Observation/intermediate Calculation → SEC Document.
- Claim → `extracted_from` → Document → Source.
- Inference → `derived_from` → recorded analytical inputs.

Unrelated judgments produce no epistemic graph edge. All judgments, including unrelated, are retained on the corresponding ModelRun node, along with diagnostic counts. This preserves inspectable evidence IDs, target IDs, rationale, assumptions, missing information and execution identity even when no relation edge is rendered.

Assessment IDs now include their model-run identity. Repeating a judgment cannot silently overwrite its earlier execution. Existing follow-up IDs and namespacing remain. The follow-up action includes diagnostic counts for that cycle. Initial assessment logs aggregate all returned judgments; each ModelRun retains its own counts, broken down by Claim, Observation, Calculation and Inference. Zero is valid; these are counts, not belief scores.

Review support/counter logic was already source-kind agnostic. Tests now explicitly verify every native kind. `supports` counts support; `weakens` and `contradicts` count counter-evidence. `context_for` has an explicit separate context count. Execution, source, requirement and candidate-explanation links do not contribute. Existing legacy graph handling remains.

The edge inspector now explicitly shows source type/ID/content, relation, target hypothesis/ID, strength, rationale, assumptions, missing information and assessment ModelRun ID. Existing source/target buttons and model-run/source traversal provide navigation without creating duplicate provenance nodes. Workspace identity, human review, filters, selection, positions and temporal cutoff are unchanged.

## Temporal and domain limits preserved

The assessor consumes evidence already admitted by the existing initial/follow-up pipelines; it does not fetch evidence or decide publication eligibility. Strict publication/date-only rules, original follow-up cutoff, SEC filing/amendment/restatement eligibility and historical peer-unavailability remain unchanged. No temporal filter was bypassed.

Generic industrial quarterly metrics remain excluded for financial institutions. SHBI/THFF deposit costs, NIM, loan-growth or peer medians are not fabricated or newly implemented. Historical peers still require dated identity metadata, absent from the current universe CSV. These unavailable states remain visible.

## Saved-case diagnostics

No saved graph was rewritten or reclassified. The following distributions are identical before/after this task, counted directly from `data/fixtures` JSON files without provider calls:

| Saved fixture | supports | weakens | contradicts | context_for |
| --- | ---: | ---: | ---: | ---: |
| investigation_axp_bac_2026-02-27.json | 1 | 0 | 0 | 17 |
| investigation_demo.json | 3 | 0 | 0 | 0 |
| investigation_gs_ual_2026-03-20.json | 0 | 0 | 0 | 11 |
| investigation_live_nvidia.json | 7 | 0 | 0 | 9 |

These are stored graph edge distributions, not reconstructed model assessment counts. Legacy files do not retain every unrelated judgment, so their unrelated counts cannot be reliably recovered. New assessment runs retain those judgments and typed diagnostics. Evaluating what a real model would now say requires a new provider execution; this offline audit does not imply improved live classification distributions.

## Validation and remaining limitations

- `source .venv/bin/activate && python -m pytest -q`: **215 passed**. Approved execution outside the sandbox was used for the existing local-socket runtime test.
- `npm --prefix frontend test`: **9 test files passed**.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed.
- `git diff --check`: passed.

Focused coverage includes each native identity, legacy claim calls, typed response validation, all allowed relation kinds, unrelated exclusion, repeated execution identity, bounded selection, descriptive/causal protocol examples, actual quarterly SEC calculation lineage, native review counts, initial pipeline wiring, SEC-only targeted follow-up, no repeated assessment of unchanged SEC nodes and no duplicate research task. Existing tests continue covering historical cutoff, future amendments, financial exclusions, peer-unavailability, failure handling, progress and replay behavior.

Tests use controlled provider responses to verify protocol/graph semantics, not to claim a model understands causality or to require visually diverse real graphs. The one updated existing assertion had expected automatic financial context despite a mocked assessor returning no judgments; it now checks the heterogeneous inputs and absence of fabricated context edges.

No live NVIDIA NIM / BookReader / web / SEC acceptance investigation was run. No commit or push was made. The lexical evidence bound can omit relevant material; model classifications remain judgments requiring review. No probabilistic aggregation, new inference generation, peer median engine or domain-specific bank metrics were added. Browser tests cover state/inspection contracts, not an automated interactive end-to-end browser session.

## Worked industrial example using supported SEC calculations

Use the existing non-financial US-GAAP quarterly test issuer **AAA**. This is a synthetic SEC Company Facts fixture, not purported live data about a public issuer. It uses the real FundamentalsService, quarterly normalization, deterministic formulas and domain projection.

At the fixture's 2026-03-01 cutoff, Q3 2025 revenue is 123 versus Q3 2024 revenue of 113. The actual implementation calculates:

- Revenue YoY: `(123 / 113) - 1 = +8.8496%`, Calculation `FIN-b7c24673f47f47b8feae`.
- Operating margin YoY: approximately **−93.5319 bp**, Calculation `FIN-294b315668cf5e1cf1eb`.
- Operating cash flow QoQ: **0%**, Calculation `FIN-4eac2e5db22cb3c4b619`.

These are separate Calculation arguments, backed by observations and eligible filing IDs. They are not converted to documentary claims. For the narrow hypothesis “AAA's operating margin deteriorated year over year,” the margin calculation can legitimately support it. Revenue growth may challenge an alternative premise of falling sales, while stable operating cash flow may weaken a cash-flow-deterioration explanation without contradicting margin deterioration. For “margin deterioration caused AAA's stock-price divergence,” that same margin result may remain context pending expectations, event timing and investor reaction evidence. A model must assess the exact supplied hypothesis; the application does not hard-code those classifications.

The offline lineage test feeds an actual service-produced revenue YoY calculation through the assessor's response contract and graph builder, then traverses its support edge back through observations to SEC filings. Its stub relation verifies plumbing, not real-world causal validity. Existing inference inputs can similarly retain a path through their source calculations while being labeled model-derived.

## Separate bank example

For SHBI/THFF the industrial quarterly exclusions remain in force. The pipeline does not manufacture margin/deposit-cost/NIM/loan-growth calculations. If a dated documentary quotation specifically establishes a hypothesis's required premise, its grounded Claim can support that hypothesis. If it conflicts with a required premise, it can contradict; if it reduces plausibility without logical conflict, it can weaken. General regional-bank pressure may remain context for a claim about disproportionate SHBI exposure or a market-price cause. Missing causal evidence remains recorded. These are conditional semantics, not claimed retrieval findings.

## Explicit answers

1. **Can ClaimGraph now create Claim / Observation / Calculation / Inference → Hypothesis epistemic relationships?** Yes. Native kinds/IDs are preserved through the shared assessor, response validation, graph builder and inspector.
2. **Can the same evidence legitimately SUPPORT a narrow hypothesis while remaining CONTEXT_FOR a stronger causal hypothesis?** Yes. Prompt v2 explicitly distinguishes them; no automatic label or causal shortcut is applied.
3. **Does the existing Missing Evidence follow-up now reassess its affected hypothesis using all relevant newly available analytical evidence rather than only grounded documentary claims?** It now considers new claims, observations and deterministic calculations through the same bounded analytical selector, including SEC-only cycles. It remains limited to affected hypotheses and at most 16 selected arguments by default; it cannot guarantee inclusion of every relevant item. The shared API also accepts explicit Inferences, but the existing cycle does not generate new Inference objects.
4. **Did any test or fixture require hard-coded relationship labels solely to manufacture supports/weakens/contradicts?** No. Saved fixtures were unchanged. Offline contract stubs deliberately return specified relation values to test each allowed branch and provenance, but no test requires any real investigation to have particular counts or every relation type.
5. **Was a real NVIDIA NIM / BookReader / web / SEC acceptance investigation run?** No. Validation used offline tests and saved-graph diagnostics only.
