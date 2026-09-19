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
a candidate does not launch research or replace the saved investigation; the existing API
only scans candidates.

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
