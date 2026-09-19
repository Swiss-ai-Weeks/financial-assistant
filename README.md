# Financial Assistant — ClaimGraph Desk

**When a strategy stops working, the reason is usually in the news. This desk
finds it and shows its evidence.**

A portfolio manager's book lagged its benchmark last month. The desk shows
*where* each trading strategy's assumption broke, lines those moments up against
the news that was public **at the time**, and asks a locally served NVIDIA
Nemotron model to explain each one with claims that are quoted, sourced and
auditable.

```
book vs benchmark ─► strategy monitors ─► anomaly ─► point-in-time news ─► Nemotron ─► ClaimGraph
   "I'm -2.6%"        VWAP · TWAP ·        "BAC/JPM       only what was       claims,      who said what,
                      trend · pairs        spread -3.4σ"   published before    hypotheses,  what supports,
                                                           the move            relations    what is missing
```

## Quick start

Requires Python 3.11+ and Node 20.19+.

```bash
make setup     # virtualenv, Python and npm dependencies, .env
make dev       # API on :8080, UI on http://localhost:5173
```

That is the whole desk: live prices, the four strategy monitors, pair scans and
the news wire need **no API key and no GPU**.

The **Explain** button needs a language model. On the GPU box:

```bash
pip install vllm
make llm       # Nemotron 3.5 Lightning 30B-A3B, one replica per H100, :8000
make search    # optional: SearXNG for wider web retrieval, then set SEARXNG_URL
```

No GPUs at hand? Put an NVIDIA API key in `.env` (see `.env.example`) to use the
same model hosted. Other targets: `make test`, `make serve` (UI and API as one
process), `make reset` (restore the demo book).

## The demo in two minutes

1. **The problem.** The strip under the top bar reads *Underperforming SPY by
   2.6%* and names the largest detractors. The desk opens on the worst one.
2. **Where it broke.** The blotter lists every moment a strategy assumption
   failed over the month. Pick a monitor in the *Strategy Monitor Marketplace*
   (VWAP, TWAP, MA Cross, Pairs) to filter the chart and the blotter.
3. **What the world knew.** Click any session on the chart: the News tab shows
   what was published that day.
4. **Add a name.** Search a company in the top bar and press *Add*. The desk
   immediately tests it for cointegrated partners and opens the spread if it
   finds one.
5. **Why.** Click *Explain →* on an anomaly. News is split at the evidence
   cutoff (admissible vs hindsight); Nemotron extracts quoted claims, proposes
   competing explanations, and weighs one against the other, stage by stage.
6. **Audit it.** *Open ClaimGraph* shows every claim, source, assumption and
   model run behind the verdict.
7. **The hardware story.** The chip icon explains the model choice and shows
   measured latency per stage.

## Documentation

- [Architecture](docs/ARCHITECTURE.md): controllers, services, repositories;
  the strategy monitors; temporal provenance.
- [Model choice](docs/MODEL.md): why Nemotron 3.5 Lightning 30B-A3B, and how it
  is served on two H100s.
- [EventKG integration](docs/eventkg-integration.md)
- API reference: <http://localhost:8080/docs> while the API runs.

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

## Static prototype dashboard

The earlier static prototype,
[`prototypes/causal-signal-dashboard-static/index.html`](prototypes/causal-signal-dashboard-static/index.html),
demonstrates how an anomaly,
causal qualification, continuation probability, and a long/short/no-trade
research signal fit together. It includes three fictional scenarios, an as-of
time slider, evidence-backed mechanism paths, criterion-level attribution, and
source-lineage traceability.

Open the file directly, or serve the repository locally:

```bash
python -m http.server 8000
```

Then visit `http://localhost:8000/prototypes/causal-signal-dashboard-static/`.

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
