# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

## Investment Evidence Review

The review workspace uses the existing React Flow graph and saved investigation JSON.
Choose a saved investigation at the top; the NVIDIA example is a saved NIM run with a
synthetic attention event. The separate **Illustrative review** example contains fictional
support, a peer-move counterpoint, an assumption, a calculation, and missing evidence.
It is not a live market investigation.

Enter a reviewer name and purpose, inspect nodes and relationships, and record a rationale
when accepting, challenging, or requesting evidence. Use **Review summary** for the primary
analytical claim and final human disposition. Approval means acceptance for that purpose,
not objective proof. A subsequent item decision or metadata edit reopens an approved case.

Review edits are stored locally in the browser; use **Export review + graph** for a JSON
copy. They are not written to the Python backend. Browser storage failures fall back to
memory with a visible message. Saved decisions are applied only to the identical graph
snapshot. Exports do not yet have an import UI.

Graph filters combine selected types/roles without changing the source graph. Use **Fit
visible nodes** after filtering, or select an item from the focus dropdown. Supporting and
counter roles come from relationships and may overlap. `competes_with` is not counted as
counter-evidence. Requirement satisfaction is shown only if explicitly recorded in
`node.data.status`; an absent status is not assessed. Source classifications use explicit
`node.data.source_classification`; calculations/inferences have a DERIVED display category.
Missing tool/query metadata stays unavailable.

The anomaly scanner remains available in **Explore market anomaly candidates**. Selecting
a candidate only selects it. Choose the model/provider for the **next** investigation,
check the timezone-aware observation/evidence cutoff, then click **Investigate candidate**.
The observation defaults to the end of the candidate day in UTC; adjust it when the actual
observation time is known. Recorded `model_run` provenance remains in the graph inspector.

Start the backend from the repository root with
`PYTHONPATH=src .venv/bin/python scripts/anomaly_api.py`, then run `npm run dev` here.
Vite proxies `/api` to port 8001. The backend requires the existing
`data/cache/market/global_demo_daily.csv` and `demo_pair_fits.json`, plus the existing
BookReader, SearXNG and inference services. Restart it after updating the market caches;
scans and investigations share the same in-memory cache snapshot.

`GET /api/investigations/models` exposes the configured model/provider pairs. NIM/Nemotron
at the existing local endpoint is the default. Operators can set `CLAIMGRAPH_MODELS` to a
JSON list of `{ "provider": "...", "model": "...", "base_url": "..." }` entries for
existing OpenAI-compatible deployments; the first entry is the default. Endpoint URLs stay
server-side. The browser cannot supply arbitrary inference URLs. No credentials change.

`POST /api/investigations` accepts `ticker_a`, `ticker_b`, `as_of` (YYYY-MM-DD),
`observed_at` (ISO timestamp with timezone), `provider`, `model`, and the candidate's
`entry` threshold. It validates the current cache date and pair, reconstructs the anomaly
from the detector's frozen fit and prices, and calls `investigate_signal` from the historical
script. The existing BookReader + SearXNG retrieval, claim extraction, hypothesis/audit and
relationship pipeline builds and returns the complete v0.2 graph. This is a synchronous HTTP
request, without a queue or persistence service. Allow long requests through any deployment
proxy. Hindsight simulation and saved-file writing remain CLI-only.

The graph and review stay visible during execution and failures. Success directly loads the
response and opens a fresh review with a unique investigation ID; source and model provenance
are retained. Export the new graph/review to keep a portable copy. Saved examples still use
explicit paths, but live investigations never read or write those paths. Previously, writing
a new JSON into `frontend/public` did not display it because the UI fetched only explicitly
listed saved filenames and had no investigation response handler.

Validation (after installing the existing lockfile dependencies):

```sh
npm test
npm run lint
npm run build
```

`npm test` uses Node's built-in test runner and needs no installed packages. Tests cover
review decisions, persistence snapshots, evidence roles, provenance, filtering, graph
adapter metadata, and all five saved graph fixtures. Browser interaction and the production
build still need verification when dependencies are available; see `../DEVELOPMENT_REPORT.md`.
