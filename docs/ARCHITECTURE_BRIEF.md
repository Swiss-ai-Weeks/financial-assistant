You are acting as a software architect for a hackathon project called ClaimGraph.

Your task is to propose a simple, comprehensible repository folder structure for the COMPLETE application.

Do not generate implementation code yet.

PROJECT PURPOSE

The system receives detected financial anomalies, investigates them using external information and tools, builds a structured evidence-based claim graph, and exposes the result through an interactive frontend.

The core pipeline is:

market / portfolio data
→ anomaly detection
→ NVIDIA NIM anomaly interpretation
→ AnomalyEvent
→ research / investigation
→ ResearchBundle
→ ClaimGraph reasoning
→ ClaimGraphResult
→ API
→ interactive frontend

IMPORTANT ARCHITECTURAL BOUNDARIES

1. Anomaly layer

This layer may be owned by another team/component.

Its output should be normalized into an AnomalyEvent.

Example conceptual fields:

- event_id
- ticker
- timestamp
- anomaly_type
- metrics
- baselines
- context
- portfolio_context

The rest of the application must NOT depend directly on the anomaly detector's internal implementation.

Use an adapter boundary.

2. Research layer

Input:
AnomalyEvent

Responsibilities:

- generate investigation queries
- generate candidate search hypotheses
- call external tools
- retrieve news
- retrieve primary/company/regulatory sources
- retrieve market data where required
- normalize retrieved items
- deduplicate syndicated material
- preserve source provenance
- perform explicit calculations needed for investigation
- preserve execution provenance

Output:
ResearchBundle

Conceptual ResearchBundle fields:

- event_id
- anomaly
- retrieved_items
- sources
- calculations
- candidate_hypotheses
- execution_trace

Candidate hypotheses are SEARCH hypotheses, not authoritative conclusions.

3. ClaimGraph layer

Input:
ResearchBundle

Responsibilities:

- formulate candidate analytical claim
- decompose claim into subclaims
- identify evidence requirements
- connect evidence and counter-evidence to claims
- distinguish:
  - observation
  - metric
  - calculation
  - assumption
  - inference
  - evidence
  - counter-evidence
  - context
  - baseline
- assess confidence / qualification
- expose missing evidence
- build graph representation
- preserve epistemic provenance

ClaimGraph must distinguish:

A. Epistemic provenance:
claim → evidence → source / calculation

B. Execution provenance:
agent → action → tool call → input → output

Output:
ClaimGraphResult

Conceptual fields:

- event_id
- claims
- subclaims
- evidence
- counter_evidence
- calculations
- assumptions
- inferences
- sources
- nodes
- edges
- execution_trace
- confidence / assessments

4. Evidence feedback loop

ClaimGraph may discover missing evidence.

Architecture should allow:

ClaimGraph
→ EvidenceRequest
→ research layer
→ additional evidence
→ updated ResearchBundle
→ ClaimGraph reassessment

Do NOT build a complicated autonomous multi-agent implementation just to support this.
A simple function/API boundary is sufficient for MVP.

5. Frontend

The frontend should support:

- anomaly summary
- key metrics
- analytical conclusion
- interactive ClaimGraph
- clickable nodes
- node inspector
- evidence inspector
- source inspection
- calculation inspection
- execution trace / provenance inspection

The user should be able to answer visually:

- what supports this?
- what contradicts it?
- what was observed?
- what was calculated?
- what was inferred?
- what assumptions were introduced?
- where did this evidence come from?
- which tool/agent generated this?
- where is evidence missing?

TECHNICAL CONSTRAINTS

This is a hackathon MVP.

Optimize for:

simple
→ correct
→ inspectable
→ visually compelling
→ demonstrable

Avoid unnecessary:

- Kubernetes
- graph databases
- authentication
- microservices
- event buses
- complex multi-agent frameworks
- production observability stacks
- large RAG architectures
- excessive abstraction

Prefer:

- one monorepo
- Python backend
- FastAPI if an API framework is needed
- Pydantic/domain models for contracts
- React frontend
- JSON fixtures
- optional SQLite only if persistence is useful
- NVIDIA NIM behind a provider abstraction
- deterministic demo fixtures
- small test suite

MODEL PROVIDERS

The application may use NVIDIA NIM as the intended runtime model.

Do not couple ClaimGraph logic directly to a specific provider.

Use a small provider abstraction such as:

LLMProvider
  ├── NIMProvider
  └── optional development provider

Do not over-engineer this abstraction.

STORAGE

For the MVP:

- ResearchBundle and ClaimGraphResult should be serializable as JSON.
- A run should be replayable from stored JSON.
- SQLite may optionally index runs.
- Do NOT require a graph database.

Example run layout:

data/runs/RUN-001/
    anomaly.json
    research_bundle.json
    claimgraph.json

DEVELOPMENT REQUIREMENT

Different parts of the team must be able to work independently.

Therefore include fixtures such as:

- anomaly_demo.json
- research_bundle_demo.json
- claimgraph_demo.json

These allow:

anomaly_demo.json
→ research development

research_bundle_demo.json
→ ClaimGraph development

claimgraph_demo.json
→ frontend development

TEAM BOUNDARY

Research developer primarily owns:

research/
tools/
retrieval
normalization
deduplication
calculations

ClaimGraph developer primarily owns:

claimgraph/
claim decomposition
evidence assessment
counter-evidence
missing evidence
graph construction
inspection frontend

Shared responsibility:

domain models / schemas / contracts

TASK

Propose the repository structure.

For each directory and important file:

1. explain its responsibility in one sentence;
2. state which pipeline object enters and leaves it where relevant;
3. identify whether it is:
   - MVP
   - useful if time permits
   - post-hackathon;
4. identify likely ownership:
   - anomaly team
   - research developer
   - ClaimGraph developer
   - shared.

Keep the structure deliberately small.

Do NOT create dozens of empty modules.

Start with the minimum physical structure needed today, then separately show how it could evolve after the hackathon.

Your response should contain:

1. Recommended MVP folder tree.
2. Explanation of each major folder.
3. The three main interface contracts:
   AnomalyEvent
   ResearchBundle
   ClaimGraphResult.
4. Ownership map.
5. Files/folders that should NOT be created yet.
6. A suggested order in which to create the files.
7. Any architectural risks you see.
