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

## Synchronous response delivery and audit identifier stability

### Root causes and changes

The observed 100–120 second investigation completed graph construction, but its
response encountered a disconnected client. Vite had no explicit long-running
proxy timeout. The handler's broad exception boundary included response writes,
so a BrokenPipeError was incorrectly treated as an application failure and caused
a second HTTP 400 write to the dead socket.

`frontend/vite.config.js` now sets both API `timeout` and `proxyTimeout` to
300000 ms. Existing target, HMR and Launchpad settings are unchanged.
`scripts/anomaly_api.py` separates request parsing/execution from completed-response
delivery. Genuine execution failures still return HTTP 400 with the original
error text. BrokenPipeError and ConnectionResetError on completed-response delivery
are logged as client disconnects, with no second response or investigation rerun.
The shared scan response uses the same delivery boundary.

The audit model sometimes returned mutated or duplicate application-owned IDs.
`src/financial_assistant/llm/hypothesis_audit.py` now uses prompt version
`hypothesis-audit-v2` with explicit opaque-ID copying rules. The initial batch call
is unchanged in shape. Only a schema-valid response failing the ID validator gets
one constrained repair call. Its prompt contains the exact allowed IDs, original
hypotheses and evidence context, and previous response, and requests preserved
content where possible without positional assignment or guessing ambiguous identity.
The repair passes through the same `_AuditResponse` model and the same deterministic
validator: no duplicates and exact set equality. A second ID failure raises the
existing ValueError; schema failures and provider errors propagate without further
retry. Application code never normalizes IDs or reassigns content by position.

ModelRun retains the actual provider/model, hypothesis-audit operation, new prompt
version and UTC creation timestamp after successful validation. Its existing frozen
schema has no metadata/details field for retry count. No extra run, fabricated
retry provenance, or schema migration was introduced; individual retry events are
not represented separately in the returned ModelRun.

### Exact files changed

- `frontend/vite.config.js`
- `scripts/anomaly_api.py`
- `src/financial_assistant/llm/hypothesis_audit.py`
- `frontend/tests/viteConfig.test.js`
- `tests/test_investigation_api.py`
- `tests/test_hypothesis_audit.py`
- `DEVELOPMENT_REPORT.md`

### Validation

- `npm --prefix frontend test`: 5 test files passed, 0 failed (Node reports 5 tests).
- `npm --prefix frontend run lint`: passed, exit 0, no diagnostics.
- `npm --prefix frontend run build`: passed, 181 modules transformed.
- `source .venv/bin/activate` then `python -m pytest -q`: 89 passed, 0 failed.
- `git diff --check`: passed.

New tests cover both completed-response socket failures without a second response,
proxy timeouts, exact IDs without retry, duplicate/mutated/missing ID repair,
successful repair with reversed order and preserved content associations, strict
failure after one repair, and initial/repaired schema rejection. Existing genuine
investigation-error, hypothesis audit, live investigation, temporal, review,
execution provenance and exact source-quote grounding tests remain passing.
No live NIM, retrieval service, or H100 browser acceptance run was performed.

### Remaining limitations

Vite's five-minute settings cannot override an NVIDIA Launchpad outer proxy limit.
If that proxy disconnects sooner, the browser can still report NetworkError even
though the backend finishes; the backend now records the disconnect honestly.
There is no result-recovery endpoint or background job infrastructure in this patch.
The H100 acceptance sequence remains: select anomaly, choose NIM/Nemotron, explicitly
Investigate candidate, wait roughly two minutes, and verify the completed graph
replaces the previous graph without a disconnect or misleading HTTP 400 and with
exact audit IDs. A repair adds one model-call latency. Outer-proxy behavior must be
checked there; async job API work would require a separate request.

The separate ticker/issuer issue originates in
`src/financial_assistant/retrieval/query_expansion.py`: its system prompt asks the
model to resolve canonical names, while `build_query_expansion_prompt` passes
ResearchTask entity/ticker strings without a deterministic issuer mapping.
`data/universe/global_equities.csv` already contains BUSE → FIRST BUSEY and
PNW → PINNACLE WEST. This metadata is not supplied to that prompt. The observed
“Buse Health” expansion and Pacific Northwest/local-news results are therefore
entity-resolution/relevance failures, not reasons to relax grounding or dates.
A future focused change should supply deterministic universe issuer metadata before
LLM query expansion. Historically eligible but irrelevant BookReader FT/WSJ pages
remain a separate relevance issue. No retrieval behavior was changed here.
Temporal rules, strict publication cutoff, hybrid retrieval, exact source spans,
prospective model selection, historical model_run provenance, explicit investigation
action, and existing graph/review preservation behavior were left intact.

## True historical time travel

### Product correction and inspection

TemporalReview filters publication availability in an existing graph. It does not
reconstruct a market, select relationships, or detect a historical anomaly. It is
now labelled **Evidence timeline**, inside the investigation. **Live / Time Travel**
controls the market workflow independently. Fictional replay examples remain
explicitly labelled teaching material.

Inspected the requested API/CLI, detector, retrieval, query expansion, graph builder,
frontend, Vite configuration, report and universe metadata. Neither
`data/cache/market/global_demo_daily.csv` nor `demo_pair_fits.json` exists in this
checkout. Their actual data/calibration dates could not be verified. The cache
producer `scripts/precompute_demo_pairs.py` defaults to 2026-09-18 and calibrates
through the prior day, selecting bounded peers using formation correlations. Such
a cache includes information after 2026-08-28 and cannot honestly be reused for
that earlier date. Its selected pair identities also reflect that later window.
The historical API never imports or consults those identities or fitted statistics.

### Market reconstruction and anti-look-ahead rules

`POST /api/anomalies/historical-scan` accepts `as_of` as YYYY-MM-DD plus `corr_min`,
`alpha`, and `entry`. It truncates prices to dates <= the request before handing
anything to the existing `scan_pairs_as_of`. A non-session resolves explicitly to
the latest available session <= D; both requested date and resolved session are
returned and displayed. Missing history returns a clear error. An old/stale cache
can resolve to an old session: always inspect the displayed resolved date.

Formation uses 252 distinct available dates strictly before the resolved session.
The existing scanner recomputes return correlations, eligible pairs, Engle–Granger,
hedge ratio/intercept, spread mean/std and other fit statistics from that window.
Monitoring evaluates only the resolved session. All available cache tickers are
considered; columns with missing formation observations are excluded by the existing
scanner. Historical mode does not reuse the live cache's current group/peer selection.
It also does not reproduce its bounded peer limit. This can change the historical
candidate universe relative to live and may be substantially slower.

The response includes formation bounds, observation cutoff, recomputation flag,
CPU execution metadata, elapsed milliseconds, candidate metrics and a scan ID.
A bounded in-memory store retains the last 16 scan snapshots. Investigation validates
the selected pair and requested date against that snapshot; browser-supplied beta,
p-values, threshold or other fitted metrics cannot replace the frozen signal.
Expired snapshots require a new scan. LIVE retains the existing scan/cache path.

**Data limitations:** this is a reconstruction from the available price cache,
not a certified point-in-time security master or vintage price database. Current
universe survivorship, historical price revisions/corporate-action adjustments,
issuer renames, exchange holidays and cross-market close times are not reconstructed.
There is no FX-normalization stage. These limitations prevent claiming a bias-free
historical backtest despite strict exclusion of future price rows and fits. The UI
explicitly displays the universe/data revision limitation. No GPU path was attempted;
full-cache profiling and an H100 benchmark were impossible without the cache/device.
CPU remains the existing reference implementation.

### Historical investigation and retrieval

A date-only investigation uses **23:59:59.999999 UTC on the selected calendar day**,
computed server-side. The market signal retains its resolved trading-session date.
For a weekend selection this allows weekend evidence available by the selected day's
end, against the explicitly displayed prior-session market signal.

The shared `investigate_signal` pipeline retains selected provider/model, hybrid
BookReader/SearXNG retrieval, exact quote validation, hypothesis generation, strict
audit ID validation/one repair, relationship assessment and v0.2 provenance graph.
BookReader retains its bounded `from_date`/`to_date` search. SearXNG discovery is
followed by publication-date checks after fetch, and strict document selection
before claim extraction. Unknown publication dates cannot become evidence;
`retrieved_at` and `event_at` do not establish availability. Date-only publications
on D are eligible at the end of D while retaining `published_date_only=true`;
intraday cutoffs remain conservative. The evidence timeline uses the same end-of-day
availability bound at JavaScript millisecond precision.

The cached universe's unambiguous ticker/name mapping is supplied to ResearchTask
before model expansion, preserving ticker aliases (BUSE/FIRST BUSEY and
PNW/PINNACLE WEST). Retrieval selection uses those task identities. The prompt tells
the model to expand, not reinterpret, known issuers. This is an identity constraint,
not proof of relevance; exact-source grounding remains mandatory. A contemporary
model's training knowledge cannot itself be rewound. Evidence admission is controlled,
but the implementation does not claim a historical model-training snapshot.

### Hindsight, replay and epistemic separation

Only **after** the investigation/graph has completed does the API call the existing
`simulate_pair_forward` (`pair-forward-v2`). Entry is the next common session's open;
horizon 1 is that session's close. Fixed signed gross-normalized notionals follow
(-1, beta) for positive z / short spread, and (+1, -beta) for negative z / long spread.
The simulator reports available 1/5/10/20-session returns, latest return, drawdown
relative to initial gross capital (including zero baseline), and first frozen-spread
equilibrium crossing. Default gross capital is 10,000 and transaction costs are zero;
this is a hypothetical mechanical position, with no borrow/slippage execution model.
Unavailable future data is reported without discarding the investigation.

Outcome lives in a separate top-level `hindsight_outcome`, never graph nodes/edges,
claim extraction, hypothesis generation, audit, relationship assessment or evidence
counts. A visually distinct collapsed **Reveal HINDSIGHT OUTCOME — NOT AVAILABLE TO
THE ORIGINAL INVESTIGATION** panel displays it. Profit does not prove a hypothesis;
loss does not disprove all reasoning.

Successful historical runs are atomically saved to `.run/replays/<uuid>.json` before
HTTP response delivery. Packets include requested/resolved dates, formation/complete
signal metrics, graph/source metadata, model provenance, temporal metadata and the
separate outcome. `/api/replays` lists completed runs; `/api/replays/<uuid>` loads them.
The saved-case selector recovers them after reconnect/reload without a model rerun.
Export review downloads the packet plus human review; Import replay accepts that
file. Private source text is not embedded in graph packets. Replay source viewing
still requires the configured corpus. Files are local prototype persistence, without
multi-user isolation or automatic retention management.

### Source-link authorization

BookReader's adapter uses `Authorization: Bearer <BOOKREADER_API_TOKEN>` and
`GET <BOOKREADER_BASE_URL>/documents/<document-id>`, returning normalized JSON text.
The browser learns only the configured base URL to recognize exact corpus links;
public HTTP(S) URLs remain normal external links. Recognized corpus links open
`/api/bookreader/documents/<id>`.

The server validates a bounded identifier alphabet, rejects traversal, embedded URLs,
query/fragment injection and encoded path separators, fixes the upstream origin to
configuration, and attaches the existing bearer header. The adapter now rejects
other origins and redirects, preventing credential forwarding. The viewer returns
only escaped whitelisted publication/date/ID/page/hash/text fields, redacts any token
occurrence, uses a restrictive CSP and disables response caching. It never returns
upstream headers, authentication configuration or detailed upstream errors. No token
is placed in a browser URL. This remains a private demo route on the existing app,
not an arbitrary URL proxy; do not publish the demo as a public corpus service.

### Detached runtime and exact H100 commands

The old start/stop names delegate to the new checkout-relative scripts. They use
nohup + setsid, detach stdin/stdout/stderr, launch the exact Python/Vite executables,
retain inherited NIM configuration, and avoid npm wrapper PID ambiguity. PID files
include the Linux process start time; status/stop verify that and the exact script
argument before signalling. Unknown occupied ports are refused, not adopted or
killed. A user-level lifecycle lock prevents concurrent start/stop races. Logs and
PID/replay files live under ignored `.run/`, created with restrictive permissions.
The frontend process does not inherit BOOKREADER_API_TOKEN. Required dependencies
and caches must already exist; startup does not install anything or use root.

From the ClaimGraph checkout on the H100:

```bash
# Optional: point to your EXISTING server-only shell environment file.
# Alternatively the starter loads .env.bookreader in this checkout if present.
export BOOKREADER_ENV_FILE=/absolute/path/to/your/existing/bookreader.env
./scripts/demo_start.sh
./scripts/demo_status.sh
./scripts/demo_logs.sh backend
./scripts/demo_logs.sh frontend
# Ctrl-C exits log following, without stopping the services.
./scripts/demo_stop.sh
```

If credentials are already exported, omit BOOKREADER_ENV_FILE. The backend uses
127.0.0.1:8001; Vite uses port 5173 and refuses automatic port changes. Existing
Launchpad host/HMR/proxy configuration is retained. Detached services survive terminal
exit; they do not auto-restart after crashes/reboots. `.run/logs` is diagnostic output
and should remain private. Saved replay recovery handles completed investigations
whose browser connection disconnected; this does not add a task queue.

### Files changed

- `scripts/anomaly_api.py`, `scripts/investigation_api.py`, new `scripts/historical_api.py`
- `scripts/investigate_historical_pair.py`, new `scripts/bookreader_viewer.py`
- `src/financial_assistant/retrieval/bookreader.py`, `query_expansion.py`
- new `src/financial_assistant/research/identity.py`
- `frontend/src/App.jsx`, `DetectorPanel.jsx`, `NodeInspector.jsx`, `TemporalReview.jsx`
- `frontend/src/temporalModel.js`, `investigationClient.js`, new `sourceLinks.js`, `index.css`
- new `scripts/demo_{common,start,stop,status,logs}.sh`, legacy start/stop wrappers, `.gitignore`
- new `tests/test_time_travel_api.py`, `test_bookreader_viewer.py`, `test_demo_runtime.py`
- new `frontend/tests/timeTravel.test.js`, this report

### Suggested 90-second demo and H100 acceptance

Prepare one successful real historical investigation ahead of the demo. Verify its
cutoff and inspect all admitted publication metadata before presenting it.

1. 0–15s: Show `demo_status.sh` after disconnect/reconnect. Choose Time Travel and D;
   Travel, show resolved session, formation bounds and dated candidate metrics.
2. 15–30s: Select a candidate and show “Investigate at D” plus NIM/Nemotron selection.
   Load its saved real historical packet to avoid waiting for inference during the talk.
3. 30–55s: Inspect evidence/relationships and the end-of-day cutoff. Open an FT/WSJ
   source through the internal viewer; verify no Unauthorized and no token in browser
   network requests/responses. Explain that Evidence timeline is an inspection tool.
4. 55–75s: Reveal the separate hindsight panel, entry definition, returns and reversion.
   State that returns neither validate nor invalidate the hypothesis by themselves.
5. 75–90s: Return to Live and run the existing scan. End on explicit human review.

Full H100 acceptance remains outstanding: real cache reconstruction/timing, private
BookReader click-through, a real historical hybrid NIM run, terminal disconnect/
reconnect on Launchpad, and live-flow browser regression. Local tests cannot replace
those deployment checks. Do not describe the fictional timeline fixture as market
reconstruction or a synthetic test as a real successful historical investigation.

### Validation results

- `npm --prefix frontend test`: **6 test files passed**, no failures.
- `npm --prefix frontend run lint`: **passed**, no diagnostics.
- `npm --prefix frontend run build`: **passed**, 182 modules transformed.
- `source .venv/bin/activate; python -m pytest -q`: **109 passed in 5.03s**, no skips.
- `git diff --check`: **passed**.

The runtime integration test required execution outside the sandbox because local
socket creation is restricted there. It starts temporary backend/frontend HTTP
services, verifies both survive the launching shell's exit, verifies repeat-start
PID stability, keeps the corpus token out of the frontend environment, and stops
only the owned processes. The test caught and fixed ownership recognition of the
backend's `python -u` command. Separate tests reject unrelated PIDs and stale kernel
start times. This validates the process lifecycle locally, not Launchpad's outer
proxy or an actual SSH disconnect.

Historical tests include real CPU fitting on synthetic price series: mutating all
future prices leaves the result identical, while changing the observation date
changes the reconstructed formation period and z-score. Existing tests cover prior
formation windows, exact session monitoring, BookReader historical query bounds,
future-publication filtering, strict quotes, model selection, audit ID repair,
forward-entry/horizon definitions and timeline behavior. New API tests cover forged
snapshot requests, end-of-day/date-only admission, rejection of undated/future
sources, execution-before-hindsight ordering and coherent replay persistence.
Source tests cover server-side bearer headers, token-free escaped output, external
origin/redirect rejection, encoded traversal rejection and ordinary public links.
No real market data, BookReader article or model response was fabricated to stand
in for the outstanding H100 acceptance run.
