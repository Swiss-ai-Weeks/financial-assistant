# EventKG-inspired event graph

## Decision

We use the modeling ideas from the
[EventKG paper](https://arxiv.org/abs/1804.04526) without requiring RDF,
SPARQL, or the EventKG dataset at runtime.

EventKG's useful contribution is the separation of:

1. canonical events;
2. source-specific statements;
3. temporal, typed relations;
4. statement-level provenance; and
5. fused information that does not overwrite its source assertions.

For this project, that becomes:

```text
market anomaly
  -> source documents
  -> atomic claims
  -> canonical event snapshot at time T
  -> accepted economic path to a company
  -> causal candidate score
  -> continuation / Avalanche score
  -> research signal
```

The event graph is an evidence-normalization layer. It does not itself claim
that an event caused a market move or that a security should be traded.

## Package layout

```text
src/financial_assistant/event_graph/
├── models.py       # Events, entities, documents, claims, relations, snapshots
├── resolution.py   # Conservative observation-to-event identity matching
├── fusion.py       # Lineage-aware, as-of proposition reconciliation
├── paths.py        # Evidence-backed economic mechanism paths
└── adapter.py      # Event snapshot -> CandidateAssessment
```

## Core objects

| Object | Responsibility |
|---|---|
| `CanonicalEvent` | Represents one real-world event across many documents. |
| `SourceDocument` | Records publication, retrieval, reporting lineage, role, and URI. |
| `Claim` | Stores one atomic proposition and its exact provenance. |
| `EventRelation` | Reifies a typed edge with validity, direction, strength, confidence, and claim IDs. |
| `PropositionResolution` | Keeps support and contradiction visible after fusion. |
| `EventSnapshot` | Freezes what was knowable at one decision cutoff. |
| `EconomicPath` | Traces the accepted mechanism from an event to the target company or instrument. |

An article is not a claim and a claim is not an event. One earnings release can
support several claims with different directions and materiality.

## Required invariants

- Use timezone-aware timestamps everywhere.
- `retrieved_at` cannot precede `published_at`.
- `extracted_at` cannot precede document retrieval.
- Historical snapshots reject event metadata updated after their `as_of_at`.
- Later claims appear only as opaque ignored IDs in an earlier snapshot.
- A correction supersedes, but never deletes, its earlier claim.
- Syndicated copies sharing a `lineage_id` contribute only one fusion weight.
- Competing credible assertions remain `contested`; fusion does not hide them.
- A graph relation requires at least one supporting claim.
- A causal path can traverse only accepted relations valid at the replay time.

These rules prevent the most damaging form of backtest leakage: using a later
correction, article, extraction, or entity state to explain an earlier anomaly.

## Fusion behavior

`build_event_snapshot(...)` groups active claims by `proposition_id`, then
compares lineage-deduplicated support and contradiction. Evidence roles use a
versioned starting policy:

| Role | Default weight |
|---|---:|
| Primary source | 1.00 |
| Independent reporting | 0.80 |
| Secondary analysis | 0.50 |
| Syndicated report | 0.35 |
| Market data | 0.00 |

These are transparent ranking heuristics, not calibrated probabilities. Change
them only through a new `FusionPolicy.version` and replay historical cases.

Unlike the original EventKG time fusion, this implementation does not blindly
majority-vote breaking-news claims. It retains dissent and uses source role,
claim confidence, and independent lineage.

## Economic relation vocabulary

The first vocabulary intentionally stays small:

- event evolution: `subevent_of`, `precedes`, `next_event`;
- direct impact: `affects`, `drives`, `impacts_metric`;
- exposure: `exposes`, `supplier_of`, `customer_of`, `competes_with`;
- market linkage: `has_instrument`, `benchmarks`;
- participation: `participates_in`.

Add a relation type only when the team can define its direction, validity, and
financial interpretation. Do not use a generic `related_to` edge in a causal
path.

## Minimal usage

```python
from financial_assistant.causal_scoring import CausalCandidateScorer
from financial_assistant.event_graph import (
    build_event_snapshot,
    candidate_assessment_from_snapshot,
)

snapshot = build_event_snapshot(
    event=canonical_event,
    entities=entities,
    documents=documents,
    claims=claims,
    relations=relations,
    as_of_at=causal_cutoff,
)

assessment = candidate_assessment_from_snapshot(
    snapshot=snapshot,
    target_entity_id="nvda",
    anomaly_id="NVDA-2024-09-03",
    anomaly_start_at=anomaly_start,
    anomaly_end_at=anomaly_end,
    as_of_at=causal_cutoff,
    materiality=materiality,
    directional_consistency=directional_consistency,
    novelty=novelty,
    market_footprint_fit=market_footprint_fit,
    additional_evidence=(market_observation,),
)

result = CausalCandidateScorer().score(assessment)
```

The returned score includes `event_snapshot_id`, `target_entity_id`, and
`economic_path_relation_ids`. The relationship and plausibility criteria also
carry the exact `claim_ids` and `relation_ids` used.

## Ingestion-agent contract

An extraction agent should return candidate objects, not mutate the canonical
graph directly:

1. one `EventObservation` per apparent event mention;
2. one `Claim` per atomic proposition;
3. candidate `EventRelation` objects backed by claim IDs; and
4. extraction confidence and a source locator for each claim.

`EventResolver` first prefers stable external identifiers. Without an exact
identifier it combines label, event type, occurrence time, and participants,
and leaves low-confidence or near-tied observations unmerged for review.

## Dashboard contract

For every displayed signal, retain this chain:

```text
signal
  -> causal score result
  -> event snapshot ID
  -> economic relation IDs
  -> atomic claim IDs
  -> source document IDs and URIs
```

The UI should never display an explanation generated only from a rationale
string. Each clickable explanation must resolve through the IDs above.

## Avalanche extension

The next layer should compare consecutive `EventSnapshot` objects rather than
mixing continuation into causal attribution. Useful continuation features are:

- rate of new independent claims;
- arrival of primary confirmation;
- new sub-events;
- expansion to customers, suppliers, and peers;
- increase in economic-path strength or materiality;
- abnormal price/volume persistence;
- syndication saturation; and
- contradictions, corrections, or retractions.

This keeps two different questions separate:

1. **What most plausibly caused the observed anomaly?**
2. **Is the information still propagating and incompletely priced?**

## Explicitly out of scope for this implementation

- automated news extraction;
- a production entity-resolution service;
- RDF or a graph database;
- calibrated causal probabilities;
- calibrated continuation probabilities; and
- live buy/sell execution.

The models are storage-independent Pydantic contracts. They can be persisted in
PostgreSQL, a document store, or a graph database later without changing the
scorer boundary.

## References

- Simon Gottschalk and Elena Demidova,
  [EventKG: A Multilingual Event-Centric Temporal Knowledge Graph](https://arxiv.org/abs/1804.04526)
- [EventKG reference implementation](https://github.com/sgottsch/EventKG)
