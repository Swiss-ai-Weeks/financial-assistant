# PYTHIA · powered by ClaimGraph

Investment workspace with Now, Past, Portfolio, Explore and persistent Investigate tabs. ClaimGraph remains the authoritative evidence, calculation and provenance engine.

See [integration architecture, limitations and acceptance commands](docs/pythia-claimgraph-integration.md).

# Financial Assistant

Evidence-backed causal attribution for financial-news anomalies.

## Event graph and source traceability

The EventKG-inspired layer turns retrieved documents into atomic claims,
canonical events, and typed temporal relations before causal scoring. It adds:

- conservative event identity resolution;
- lineage-aware claim fusion without erasing contradictions;
- immutable historical snapshots at a strict as-of time;
- evidence-backed economic paths from an event to a company or instrument;
- claim, relation, document, and policy IDs carried into the score result.

The implementation is storage-independent and does not require RDF or a graph
database. See [the EventKG integration guide](docs/eventkg-integration.md) for
the architecture, invariants, ingestion contract, and Avalanche extension.

## First contribution: causal candidate scoring

The package contains a deterministic scorer that ranks an event cluster as a
possible explanation for an observed price or volume anomaly.

The scoring unit is:

```text
(market anomaly, candidate event cluster, affected company)
```

It is deliberately **not an individual article**. Articles, filings, market
observations, and ontology facts are evidence for or against the event
hypothesis. This prevents ten syndicated copies of one wire story from looking
like ten independent confirmations.

The scorer returns:

- a 0–100 **rank score**, not a claimed probability of causality;
- an immutable snapshot of the policy and weights used to produce it;
- an eligibility and evidence-coverage status;
- every component score with rationale and evidence IDs;
- the complete source records referenced by those evidence IDs;
- contradictory-evidence strength;
- evidence ignored because it arrived after the causal cut-off;
- any caps caused by weak or missing core evidence.

## Criteria

| Criterion | Produced by | Meaning |
|---|---|---|
| Temporal fit | Scorer | Was supporting public evidence available before or during the anomaly? |
| Relationship directness | Ontology/model | How directly does the event connect to the company? |
| Economic plausibility | Model/human | Is there an explicit event → business driver → valuation mechanism? |
| Materiality | Model/financial rules | Is the effect large relative to the company's baseline? |
| Directional consistency | Market model | Does the mechanism's sign match the abnormal move? |
| Source independence | Scorer | How many original reporting lineages support it? |
| Primary-source support | Scorer | Is there a supporting filing, issuer release, regulator, or first-party report? |
| Novelty | Retrieval/embedding model | Is the event unusual relative to recent company events? |
| Market-footprint fit | Market model | Did the company and relevant peers move in the pattern the event predicts? |
| Contradictory evidence | Scorer | How strong are independent contradictory lineages relative to support? |

Semantic criteria may be proposed by an LLM, ontology service, market model, or
human. The LLM does not calculate the final score. Cut-off enforcement,
lineage deduplication, penalties, weighting, and classification remain
deterministic and testable.

## Default formula

```text
base =
    0.18 × temporal_fit
  + 0.14 × relationship_directness
  + 0.14 × economic_plausibility
  + 0.12 × materiality
  + 0.10 × directional_consistency
  + 0.08 × source_independence
  + 0.08 × primary_source_support
  + 0.06 × novelty
  + 0.10 × market_footprint_fit

score = 100 × max(0, base − 0.25 × contradiction_strength)
```

The defaults are versioned heuristics for ranking. They must be calibrated
against labelled historical replays before anyone interprets them as
probabilities.

## Usage

```python
from datetime import UTC, datetime

from financial_assistant.causal_scoring import (
    CandidateAssessment,
    CausalCandidateScorer,
    CriterionMethod,
    CriterionScore,
    EvidenceItem,
    EvidenceRole,
    EvidenceStance,
)

release = EvidenceItem(
    evidence_id="hp-release",
    source_name="HP Investor Relations",
    source_uri="https://investor.hp.com/",
    published_at=datetime(2024, 5, 29, 20, 5, tzinfo=UTC),
    lineage_id="hp-q2-2024",
    role=EvidenceRole.PRIMARY_SOURCE,
    stance=EvidenceStance.SUPPORTS,
)

market_close = EvidenceItem(
    evidence_id="hpq-market-close",
    source_name="Market data",
    published_at=datetime(2024, 5, 30, 20, 0, tzinfo=UTC),
    lineage_id="hpq-2024-05-30",
    role=EvidenceRole.MARKET_DATA,
    stance=EvidenceStance.SUPPORTS,
)

def judged(value: float, evidence_id: str) -> CriterionScore:
    return CriterionScore(
        value=value,
        rationale="Structured assessment with a traceable evidence item.",
        evidence_ids=(evidence_id,),
        method=CriterionMethod.MODEL_JUDGMENT,
    )

assessment = CandidateAssessment(
    anomaly_id="TECH-007",
    candidate_event_id="hp-q2-2024-results",
    anomaly_start_at=datetime(2024, 5, 30, 13, 30, tzinfo=UTC),
    anomaly_end_at=datetime(2024, 5, 30, 20, 0, tzinfo=UTC),
    as_of_at=datetime(2024, 5, 30, 20, 0, tzinfo=UTC),
    evidence=(release, market_close),
    relationship_directness=judged(1.0, "hp-release"),
    economic_plausibility=judged(0.9, "hp-release"),
    materiality=judged(0.75, "hp-release"),
    directional_consistency=CriterionScore(
        value=1.0,
        rationale="The expected and observed abnormal-return signs match.",
        evidence_ids=("hpq-market-close",),
        method=CriterionMethod.MARKET_MODEL,
    ),
    novelty=judged(0.8, "hp-release"),
    market_footprint_fit=CriterionScore(
        value=0.95,
        rationale="HPQ materially outperformed QQQ and relevant peers.",
        evidence_ids=("hpq-market-close",),
        method=CriterionMethod.MARKET_MODEL,
    ),
)

result = CausalCandidateScorer().score(assessment)
print(result.model_dump_json(indent=2))
```

## Safeguards

1. Supporting news first published after the anomaly cut-off is ineligible as a
   public-news cause.
2. A semantic value without evidence IDs is treated as missing.
3. A criterion that depends on post-cut-off evidence is discarded entirely.
4. Repeated syndicated stories sharing one `lineage_id` count as one source.
5. Missing temporal, relationship, or economic-plausibility evidence yields
   `insufficient_evidence`.
6. All timestamps must be timezone-aware.

For historical replay, set `as_of_at` to the simulated decision time. Never
attach later news or future prices to a criterion: the scorer will ignore the
late evidence, but upstream feature generation must also observe the cut-off.

## Interactive dashboard

[`dashboard/index.html`](dashboard/index.html) demonstrates how an anomaly,
causal qualification, continuation probability, and a long/short/no-trade
research signal fit together. It includes three fictional scenarios, an as-of
time slider, evidence-backed mechanism paths, criterion-level attribution, and
source-lineage traceability.

Open the file directly, or serve the repository locally:

```bash
python -m http.server 8000
```

Then visit `http://localhost:8000/dashboard/`.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The tests also run without pytest:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The Pydantic request and result models expose JSON Schema through
`model_json_schema()`. This keeps the core framework-independent while making
it straightforward to wrap as a typed NeMo Agent Toolkit function or a custom
workflow evaluator.
