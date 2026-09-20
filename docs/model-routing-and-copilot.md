# Model routing and Copilot

ClaimGraph remains authoritative. Copilot is advisory UI assistance, stored in the
mounted investigation workspace, separate from graph nodes and review decisions.
Each workspace retains its manual analysis-model selection and independent panel
state while switching tabs. Reloading a page clears Copilot conversation state.

## Three planes

- **Interaction:** explain the current graph, selection, calculations, provenance,
  temporal eligibility; select nodes, filter, fit, or open the inspector.
- **Analysis:** investigation and existing missing-evidence follow-up use the
  workspace analysis model. Other analytical questions produce labelled commentary.
- **Frontier:** explicit second opinions only. Never a fallback, never graph mutation.

Routing uses explicit request-plane controls and a small deterministic intent
matcher, not a model selector LLM. Read-only questions prefer healthy local models
with the interaction role, in registry order. If unavailable, the selected local
analysis model is the fallback. Analysis uses the selected workspace model only.
A response that asks for analysis is passed once to that workspace analysis model;
both execution records are returned. Frontier uses the first healthy eligible
frontier entry, only following an explicit frontier request. There is no fallback
to frontier on failures. Ambiguous analytical wording can be routed explicitly
using the plane selector.

## Registry and configuration

Set `CLAIMGRAPH_MODELS` to a nonempty JSON list before starting the existing API.
No endpoints are discovered or provisioned. Legacy `provider`, `model`, `base_url`
entries remain valid. Default roles are `analysis`; output budget is 8192;
loopback hosts default to local, other hosts to external. Explicit `locality: local`
is an operator trust declaration for a locally controlled endpoint (including LAN).
Do not mark a public endpoint local.

This single-model configuration runs the whole application:

```json
[
  {
    "id": "nemotron-super",
    "label": "Nemotron Super 49B",
    "provider": "nvidia-nim",
    "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "base_url": "http://127.0.0.1:8000/v1",
    "roles": ["analysis"],
    "locality": "local",
    "max_tokens": 8192,
    "capabilities": {"no_think": true, "json_object": true},
    "auth_env": null,
    "timeout_seconds": 120,
    "temperature": 0
  }
]
```

Later, add an entry for your manually provided fast endpoint using
`roles: ["interaction"]`, an explicit model/endpoint, `max_tokens: 2048`, and its
actual capabilities. Add a comparator with `roles: ["frontier"]`,
`locality: "external"`, and `auth_env` naming its server-side credential variable.
No example fast/frontier endpoint is installed or hard-coded.

Missing capabilities default to JSON-object support and no `/no_think`, except
that the exact existing Nemotron model retains its legacy `/no_think` setting.
The generic provider itself defaults to no model-specific prefix. Explicit
capabilities override these registry defaults. `max_tokens` is the **output token
budget**, not model context length or prompt length.

Authentication values are read only on the server and sent as bearer headers.
Missing credentials fail safely. The public model list exposes identity, label,
roles, locality, output budget, and availability; no endpoint URLs, environment
variable names, headers, or secrets. Health probes use only configured `/models`
URLs (normally `/v1/models`), have two-second timeouts, and require the configured
model ID in the response. Optional offline entries remain listed as unavailable.
Health probes run on model-list requests and before Copilot routing. Ordinary
investigation pipelines call the configured endpoint directly, preserving their
existing execution behavior.

## External egress

`CLAIMGRAPH_EGRESS_POLICY=local_only` is the default. Every provider completion and
health probe checks policy. Unknown policy values fail closed. To opt in, set:

```sh
export CLAIMGRAPH_EGRESS_POLICY=external_allowed
```

Then explicitly select Frontier comparison or ask for a frontier second opinion.
The compact visible graph context may contain private information, so this is an
explicit authorization to transmit that projection. No raw BookReader documents
or automatic private-evidence retrieval is added. Interaction never chooses an
external model. An external analysis entry can only run when selected explicitly
as the workspace model and egress is allowed. Such a selection authorizes the
existing analysis pipeline's inputs, which may include private retrieved evidence.

Blocked, unconfigured, unauthenticated, and unavailable Copilot routes return a
structured `code` and `error` via `POST /api/copilot`. They never silently switch
to another plane.

## ViewContext and actions

`buildCopilotViewContext` projects the temporal graph deterministically: workspace
and replay identity, selected node or edge, hypothesis labels, type/relation counts,
up to 20 compact nodes, direct neighbourhood edges, calculation fields, source
references, publication/retrieval dates, and current filter/cutoff/turn state.
It excludes raw document bodies, HTML, hindsight outcomes, and React state. A selected
item outside the cutoff retains its explicit unavailable/unknown temporal status so
Copilot can explain why it is excluded.
The client enforces a 22 KB UTF-8 cap with explicit truncation; the server validates
a strict nested schema and a 24 KB cap. Summary counts describe the temporal graph;
filters describe what is currently being shown. Large or distant provenance must
be inspected by selecting its node. Missing information should be acknowledged.

Response schema: `answer`, `route`, optional `ui_action`, optional
`analysis_request`. Actions are only `none`, `select_node`, `show_supporting`,
`show_counter`, `show_kind`, `clear_filters`, `fit_graph`, `open_provenance`.
Unknown fields/actions and IDs outside the supplied projection are rejected
server-side. The UI checks node IDs again against the current temporal graph before
applying an action. This client-owned graph prototype does not have a server-side
canonical graph store; the server validates the supplied projection, not a persisted
workspace identity. Actions cannot specify JavaScript, tools, URLs, paths or state.

Copilot prose never creates Claim/Evidence/Inference nodes, relationships, or
resolution decisions. A suggested missing-evidence request presents a human-operated
button calling the existing follow-up handler with the current workspace model.
No new retrieval/reassessment pipeline is introduced. Frontier is commentary only.

## Execution and voice

Existing `ModelRun` records now have optional routing, model identity, locality,
output budget, finish reason, latency and provider-reported token usage. Copilot
returns that same structure outside the graph, with workspace/selection and prompt
version `copilot-v1`. Parallel analysis calls keep completion metadata thread-local.
Unknown usage stays absent; it is never estimated. Existing repair operations retain
metadata for their final completion. The inspector shows analytical ModelRun data;
the panel exposes Copilot execution JSON.

Text is always available. Browser `SpeechRecognition`/`webkitSpeechRecognition`
and `speechSynthesis` are optional; absent or failed recognition leaves text usable.
No cloud speech SDK is added. Browser speech recognition itself may depend on a
browser/vendor service; the inference egress policy does not control that service.
Use text when that is inappropriate for the data. Voice is never started automatically.

## Validation and deliberate limits

```sh
source .venv/bin/activate
pytest -q
cd frontend
npm test
npm run lint
npm run build
cd ..
git diff --check
```

Tests mock inference; normal startup needs no frontier model. No containers/models,
GPU configuration, Kubernetes, database, agent framework, recursive agents, automatic
discovery, or arbitrary tool execution are provided. Copilot keeps only the current
reply; execution history is not persisted in a new database or graph.

Live acceptance remains: verify each configured endpoint's `/models` identity and
JSON capabilities; exercise interaction fallback and endpoint failure; check actual
provider token usage/finish reasons; test two workspaces and time travel; try browser
microphone permission/speech support; and explicitly test frontier blocking and
allowed egress with data approved for transmission. No live inference is needed for
the automated suite.
