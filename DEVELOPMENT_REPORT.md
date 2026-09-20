# ClaimGraph — Investment Evidence Review

Session: 2026-09-19. Branch: `feature/institutional-review`.

## 1. Original architecture

- Clean working tree at entry; HEAD `8e8c53c`. No pre-existing user edits were overwritten.
- React 19 / Vite frontend, React Flow 12 graph, generic node/relationship inspector.
  `App` fetched the saved NVIDIA investigation; selected item and detector candidate were
  separate React state. Candidate selection did not change the investigation graph.
- Python domain models and deterministic Pydantic graph builders. Current v0.2 nodes:
  anomaly, hypothesis, claim, assumption, evidence_requirement, missing_evidence,
  observation, calculation, inference, document, source, model_run.
- v0.2 epistemic roles are edges (`supports`, `contradicts`, `weakens`, `context_for`),
  not replacement node types. Source provenance uses `extracted_from` / `published_by`;
  calculation provenance uses `calculated_from` / `derived_from`; execution uses
  `produced_by` and relationship `model_run_id`. v0.1 has primary/subclaims and explicit
  evidence/counter-evidence nodes; it remains untouched.
- Scanner is a small HTTP service backed by market caches. Research/retrieval and NIM
  integrations are Python modules/scripts, not an end-to-end investigation HTTP route.
- NVIDIA saved example contains a **synthetic** attention event, real saved model-run
  metadata, assumptions and gaps, but no counter relationships or calculations.
- No applicable AGENTS.md was found. Existing styles, graph components, domain/schema,
  builders, scanner route, representative fixtures and existing test examples were inspected.

## 2. Implemented

- Human-owned review overlay: ID, investigation ID, title, owner, purpose, dates,
  selected analytical claim, status, per-item review state and decision history.
- Restrained institutional header and graph-derived counts. Supporting/counter counts
  deduplicate item IDs, can overlap, and preserve their original epistemic types.
- Explicit requirement satisfaction counts; missing statuses remain unassessed.
- Browser-local persistence on edits/decisions, visible storage fallback and JSON export
  containing the review plus complete graph. A changed graph snapshot invalidates reuse
  of previous decisions. No backend persistence or new dependencies.
- Human Accept / Challenge / Request evidence controls for nodes and relationships;
  name and rationale required. Case approval additionally requires a purpose. Item
  acceptance never changes evidence types or resolves missing evidence. Outstanding item
  challenges retain the challenged case status. New decisions/metadata edits reopen approval.
- Review summary with selected hypothesis/claim, recorded assessment, scoped support and
  counter items, investigation-wide assumptions, gaps, calculations, sources and history.
- Graph type/role filters preserve graph data and layout state. Dynamic type lanes avoid
  collisions between larger groups; node type labels, support/counter badges, explicit
  missing-evidence styling, fit-visible control and keyboard-accessible focus selector.
- Extended existing inspector: relationships and endpoints; source/document navigation;
  model execution records, including relationship assessment runs; retained raw metadata;
  safe HTTP(S) source links and explicit unavailable tool/query/validation fields.
- Lightweight source classification display: explicit metadata, DERIVED for calculation /
  inference, otherwise Unclassified. No publisher-based guesses or reliability scores.
- Saved-investigation selector includes both historical pair examples, original fixtures,
  and a separate clearly labelled fictional review fixture covering the full demo narrative.
- Existing detector remains available in a collapsible panel, with accurate messaging that
  candidate selection does not generate a new investigation.

## 3. Files changed

| File | Responsibility |
| --- | --- |
| `frontend/src/App.jsx` | Review orchestration, saved cases, storage/export, retained detector |
| `frontend/src/ReviewWorkspace.jsx` | Header, summary, human actions/history |
| `frontend/src/reviewModel.js` | Pure review transitions, counts, filtering, provenance, persistence |
| `frontend/src/ClaimGraph.jsx` | Filters, typed node rendering, stable layout state, focus |
| `frontend/src/graphAdapter.js` | Dynamic lanes, restrained counter-edge styling |
| `frontend/src/NodeInspector.jsx` | Extend source/execution inspection and human review |
| `frontend/src/index.css` | Institutional styling and responsive layout |
| `frontend/public/investigation_review_demo.json` | Separate fictional demonstration fixture |
| `frontend/tests/reviewModel.test.js` | Review/graph/fixture behavioral tests |
| `frontend/tests/graphAdapter.test.js` | Layout and provenance preservation tests |
| `frontend/package.json` | Dependency-free `npm test` command |
| `frontend/README.md` | Usage, semantics, persistence limits and validation commands |
| `DEVELOPMENT_REPORT.md` | Session handoff |

Backend, runtime configuration, existing fixtures and package lockfile were not changed.

## 4. Commits and push

**No commits created.** An attempted focused `git add` / commit failed because `.git`
was mounted read-only: `Unable to create .../.git/index.lock: Read-only file system`.
Per the user's instruction, escalation was skipped and unrelated implementation continued.
All edits remain in the working tree; no files were staged. No history was rewritten.

Suggested commit groups once Git is writable:
1. Add human-owned review model and evidence selectors.
2. Add institutional review header, summary and human controls.
3. Add graph filters and source/execution inspection.
4. Add illustrative review fixture, tests and development documentation.

Origin is configured as `https://github.com/Swiss-ai-Weeks/financial-assistant.git`.
Push was skipped: there are no new commits, build validation is blocked, and network /
authentication was not attempted. Do not push to the default branch.

## 5. Tests and results

- `npm test --prefix frontend`: passes both test files. Direct execution reports **17
  passing tests** (15 review/model/fixture tests and 2 graph adapter tests).
- Tests cover identity/dates, evidence/counter deduplication, immutable filters, source and
  model provenance (including relationship assessments and cycles), human transitions,
  outstanding challenges, missing-evidence preservation, explicit satisfaction status,
  classification fallbacks, scoped summaries, legacy edge direction, snapshot persistence,
  malformed saved review recovery, graph positions and all five fixtures' IDs/endpoints.
- All frontend JS/JSX source files compile with the available system Babel React preset.
  System ESLint on compiled output reports no undefined or unused variables. This is a
  limited fallback, **not** the project's lint command, React rendering, or Vite build.
- `git diff --check`: passes.
- `python3 -m pytest -q`: blocked at startup; `No module named pytest`.
- `npm run build`: blocked; `vite: not found`.
- `npm run lint`: blocked; installed project dependencies are absent and system ESLint
  6.4 cannot use the project's modern flat configuration.
- `npm ci --offline --ignore-scripts`: failed with `ENOTCACHED` for zustand. No lockfile
  changes. Online installation was skipped under the user's no-blocking-network instruction.
- Browser rendering, interaction, download, localStorage integration and responsive visual
  inspection were **not tested** because the frontend dependencies/browser tooling are absent.
- One test invocation initially used the wrong relative path; the corrected direct commands
  subsequently passed. No metrics or production-build success are inferred from syntax checks.

## 6. Verified working portions

The pure review model, graph selectors, fixture invariants, provenance resolution, layout
adapter and serialization/restore logic pass their tests. The UI implementations compile
and pass limited static checks, but their rendered behavior still requires a browser smoke test.

## 7. Partial features

- Review persistence is local to one browser, saved on edits/decisions. Export exists;
  import, server persistence, cross-browser collaboration and authenticated identity do not.
- Existing v0.2 hypotheses remain hypotheses; no artificial subclaims or causal verdicts
  are generated. The initially selected hypothesis is the first recorded candidate, not
  a ranking. The reviewer can change it in the summary.
- Tool calls, retrieval queries and validation states are displayed when supplied in item
  metadata; most current data records only model runs. No fabricated execution chain.
- Source classifications and satisfaction states exist in the new fixture; existing saved
  investigations generally have no such metadata and display honest fallbacks.
- Evidence requests are human review records, not automated research jobs.

## 8. Known issues and limits

- Full frontend/backend checks and visual verification remain blocked as described above.
- Large graphs initially fit the whole case and may require zoom/focus; filtering intentionally
  hides edges whose endpoints are hidden. Inspector references still use the complete graph.
- Review history is a local editable prototype record, not a tamper-proof institutional audit.
- Summary support/counter lists show direct links to the selected claim; assumptions, gaps,
  calculations and sources are explicitly labelled investigation-wide. No transitive verdict
  or source-independence assessment is implied.
- The existing detector API needs its market caches and running service. This session did not
  verify scanning or connect candidate selection to research generation.
- Existing provider dates/content were not externally verified. The fictional example must
  never be presented as actual market evidence or actual executed model/tool output.

## 9. H100 / NIM verification

No NVIDIA/HPE runtime configuration was modified. On the H100 machine verify NIM endpoint,
model availability, credentials, hypothesis generation/audit, extraction, relationship
assessment, BookReader/web retrieval and generated JSON compatibility. Replay the resulting
output through the UI and verify execution/source links. GPU services were not invoked here.

## 10. Exact next five highest-value tasks

1. In a writable development checkout install the existing frontend/Python dependencies;
   run `npm test`, `npm run lint`, `npm run build`, and `python3 -m pytest -q`; fix any failures.
2. Run a browser smoke test: saved-case switching, filter/drag/focus, edge inspection,
   accept/challenge/request, summary approval, refresh persistence, export, narrow screens;
   inspect spacing and graph visibility on the actual demo display.
3. Create the focused feature-branch commits listed above and push only after checks pass.
4. On H100 generate one real historical-event investigation with NIM/retrieval, preserve
   sources and model runs, and add recorded retrieval tool/query metadata where available.
5. Connect detector candidates to the existing investigation script through one small job/API
   boundary with visible progress/errors; preserve separate saved/illustrative replay modes.

## 11. Suggested demo flow (browser verification pending)

1. Open a saved GS/UAL or AXP/BAC historical investigation; explain that it is replayed output.
2. Enter reviewer name and review purpose; show case identity and evidence/gap counts.
3. Choose a candidate hypothesis in Review summary; inspect its supporting relationships.
4. Switch to **Illustrative review** and explicitly introduce the fictional teaching case.
5. Filter supporting evidence, then counter-evidence. Use Fit visible nodes / focus selector.
   Inspect the peer-return observation, its weakening rationale and market-data source.
6. Inspect the revenue-exposure calculation, underlying observations and filing metadata.
   Show the assumption and unresolved revenue-recovery evidence gap. Explain why a
   satisfied numerical requirement does not establish the overall causal explanation.
7. Inspect a produced-by link and model metadata; contrast recorded metadata with the explicit
   unavailable execution provenance on the manually authored illustrative counterpoint.
8. Record a Challenge or Request evidence with a rationale. Show the node badge, case status
   and review history. Missing evidence remains in the graph.
9. Return to Review summary, discuss what is and is not justified, and optionally approve for
   the stated purpose with qualifications. Export the case plus graph for human scrutiny.

## Temporal provenance extension — 2026-09-20

### Architecture inspected and minimum extension

The v0.2 builder serializes domain document metadata into `node.data`; sources are
publisher identities without publication timestamps. Claims/observations point to
sources via `extracted_from`; calculations and inferences use `calculated_from` and
`derived_from`. `produced_by` and `model_run_id` retain execution provenance.
Anomaly adapters put the explicit historical `observed_at` in anomaly metadata and
`detected_at`. No event timestamp is inferred from either field.

BookReader receives `from_date`/`to_date`; SearXNG receives date-context queries
(the provider itself does not translate `as_of` into a separate HTTP date filter).
Retrieval service checks publication dates and the historical investigation script
admits only known eligible publications. Date-only uncertainty is preserved.
`investigate_signal` is shared by live investigation and historical CLI work; the
CLI additionally computes and saves forward simulations separately. The historical
scanner uses CPU pair fits/cointegration; no statistical algorithm was changed.
Saved/live graphs use the same workspace; model selection remains for the NEXT run.
`graphAdapter` supplies layout/data, `ClaimGraph` applies type/role filters, and
`NodeInspector` deliberately traverses the full graph. These structures are retained.

### Model and files

No schema version change or dependency added. `RetrievedDocument.event_at` is optional;
its default is unknown. The builder adds the recorded investigation `observed_at` to
document metadata. Existing `published_at`, `published_date_only`, `retrieved_at`, and
model execution timestamps retain their meanings. Optional
`data.temporal_role: hindsight_outcome` marks outcomes.

Files: `frontend/src/temporalModel.js` (pure dependency/status/view functions),
`TemporalReview.jsx` (timeline and comparison), `App.jsx` (cutoff state),
`ClaimGraph.jsx` (composed filtering/status badges), `NodeInspector.jsx` (dates/status),
`reviewModel.js` (eligible role counts), `App.css`,
`frontend/public/investigation_temporal_demo.json`,
`frontend/tests/temporalModel.test.js`, `src/financial_assistant/domain.py`,
`src/financial_assistant/claimgraph/builder_v2.py`, and this report.

### Exact behavior and compatibility

Default view is At anomaly. Steps use actual recorded publication bounds; Latest
shows undated evidence with an explicit unknown badge. Earlier views exclude unknown
and future evidence. Date-only items become eligible on the following UTC day;
this is a conservative availability bound, not an asserted publication time.
Retrieval/event dates never establish publication. Derived items require eligible
input paths; cycles, absent inputs, and missing timestamps remain unknown.
Publisher identities are shown with eligible documents as undated provenance context.
Hypotheses, assumptions, requirements, gaps, anomaly and model runs remain labelled
investigation context, not claims of contemporaneous execution or knowledge.
Support/counter edges and counts require eligible evidence. Outcomes never enter
support edges or evidence counts, even in Latest; they have a separate outcome panel.

Cutoff changes preserve the original graph, review overlay, selected node, graph
layout and type/role filters. Header and summary use the temporal view; inspector
keeps the complete record and warns that selected items may be hidden/future.
THEN/NOW compares eligible support/counter counts, gaps and later documents; it does
not invent resolved gaps, changing causal scores, or predictive success.
Existing saved fixtures load without conversion. Existing real replay JSON is unchanged.
The new teaching replay is explicitly fictional, including its later correction,
weakening edge and 2% outcome; it is not real market evidence.

### Validation

- `npm --prefix frontend test`: all 4 test files passed, including 9 new temporal
  test cases covering pre/post cutoff, unknown/retrieval/event dates, dependency
  propagation, cycles, immutable review/selection round-trip, composed filters,
  hindsight exclusion, date-only bounds, and every saved fixture.
- `npm --prefix frontend run lint`: passed.
- `npm --prefix frontend run build`: passed.
- `source .venv/bin/activate` then `python -m pytest -q`: 79 passed, including
  existing live investigation tests, after the domain/builder changes.
- `git diff --check`: passed.
No external inference/retrieval request or browser end-to-end session was performed.
State preservation is covered at the pure model/serialization level, not a mounted
React interaction test.

### Limitations and GPU decision

Strict historical graphs cannot display later news that was never retrieved. Their
timeline may have only At anomaly and Latest. Real CLI outcome sidecars are not
joined automatically; the UI honestly reports no recorded outcome in those graphs.
The full multi-step demonstration is fictional; a verified real replay with later
news remains future work. No timestamp backfill, retrospective model rerun, gap
resolution inference or temporal reassessment of model-authored narrative is performed.
Context nodes describe the saved investigation, not a historical model execution.
Date-only interpretation follows the existing UTC date-carrier convention.

GPU work intentionally deferred after inspecting the CPU architecture. No CuPy
installation, device claim, performance claim, or benchmark was made. The cached
pair count alone does not establish a useful GPU workload; measurement would be
required before choosing a screening backend.

### Run on the H100

From the repository root, in separate terminals (retain existing provider/retrieval
environment configuration):

```bash
PYTHONPATH=src .venv/bin/python scripts/anomaly_api.py
```

```bash
npm --prefix frontend run dev -- --host 0.0.0.0
```

Open the Vite URL printed in the terminal. No GPU-specific setup is needed for
this temporal view. Saved replay works without model calls; live investigations
use the existing configured BookReader/SearXNG and selected NIM/Nemotron provider.

### Suggested 90-second demo

1. 0–15s: Select a real anomaly in the detector; show the explicit cutoff and next-run
   provider. Open an existing real historical case or an already completed live run
   (do not budget an expensive investigation inside the 90 seconds).
2. 15–30s: Show At anomaly, inspect an eligible document and an unresolved gap.
   Inspect actual BookReader/SearXNG provenance where recorded; absent fields remain
   unavailable. Show its actual model_run provider/model, independent of next-run selection.
3. 30–40s: Explain that strict historical retrieval cannot contain future news.
   Select “Fictional temporal replay · teaching case”, explicitly identifying it as fiction.
4. 40–60s: At anomaly, show supporting items and the assumption/gap. Move to the later
   publication step; the fictional correction and weakening relationship enter.
5. 60–75s: Compare THEN/NOW counts. Select Latest and inspect the separate fictional
   realised outcome; emphasize that it does not prove the original hypothesis.
6. 75–90s: Enter a reviewer and record a challenge/request for evidence with rationale.
   End on the human review, not a trading recommendation. There is no GPU screening
   provenance to demonstrate in this implementation.
