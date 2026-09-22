# EventLens:

**Investigating stock market anomalies through financial news, LLM-based analysis, and auditable event scoring.**

NewsTrace detects unusual price/volume movements, retrieves financial news around each anomaly, groups related events, and uses an LLM to investigate potential explanations.

Instead of treating an LLM explanation as fact, NewsTrace keeps the full evidence trail and applies deterministic validation and scoring before presenting candidate events.


## How it works

Market Data → Anomaly Detection → News Retrieval → Event Grouping
→ LLM Investigation → Evidence Validation → Event Scoring → Audit Report

The project combines deterministic market-data analysis, local news
retrieval, LLM-assisted evidence review, structured candidate scoring,
evidence tracking, and audit-oriented reporting. It is designed to
identify **plausible explanatory events without presenting them as
proven causes of market movements**.

## Problem

Large price moves accompanied by unusual trading volume are
straightforward to detect statistically. Explaining why they occurred is
more difficult.

A naive workflow can easily conflate several different signals:

-   a statistically unusual market day,
-   a news article that happens to mention the company,
-   a high retrieval/relevance score,
-   an LLM-generated explanation,
-   and evidence of actual causation.

This project keeps those stages separate.

It first detects anomalies from market data, then retrieves and ranks
news around selected anomaly dates. News groups are reviewed by an LLM
for documented events and possible mechanisms. Accepted hypotheses are
passed through an evidence-linked scoring layer and conservative event
grouping before being rendered into an auditable report.

Scores and hypotheses are treated as **ranking and investigation aids,
not causal proof**.

## Architecture

``` mermaid
flowchart TD
    A[User query] --> B[Financial Agent]
    B --> C[Market Data<br/>yfinance]
    C --> D[Anomaly Detection<br/>20-day volume z-score + daily return]

    D --> E[anomalies.json]
    E --> F[Anomaly Selection]

    F --> G[Finnhub News Ingestion]
    G --> H[(SQLite News Store)]

    H --> I[News Retrieval & Heuristic Ranking]
    I --> J[News Event Grouping]

    J --> K[LLM Investigation<br/>one request per selected group]
    K --> L[Validation & Review Flags]

    L --> M[Candidate Assessment]
    M --> N[Deterministic Candidate Scoring]
    N --> O[Scoring Sidecar]

    O --> P[Conservative Event Grouping]
    P --> Q[Event Ranking / Representative Assessment]

    H --> R[Offline Evidence Graph]
    E --> R

    Q --> S[Clean Audit Report]
    K --> S

    R --> T[Evidence Appendices]
```

The important boundary is between **model judgment and deterministic
processing**. The LLM can propose an event, mechanism, evidence quote,
relationship class, and semantic criterion assessments. Python code owns
anomaly calculation, evidence constraints, scoring aggregation, review
flags, event grouping, stale-output checks, and report generation.

## Pipeline

### 1. Market anomaly detection

[`utils/market_analysis.py`](utils/market_analysis.py) downloads
adjusted market data through `yfinance`.

For each trading day, the detector calculates:

``` text
volume_mean_20d = mean(previous 20 trading days)
volume_std_20d  = std(previous 20 trading days)

volume_zscore =
    (current_volume - volume_mean_20d)
    / volume_std_20d
```

The current anomaly rule is:

``` text
abs(volume_zscore) > 2
AND
abs(daily_return) > 2%
```

The rolling volume statistics use `shift(1)`, so the current day's
volume is not included in its own baseline.

The resulting dates, returns, close prices, volume z-scores,
methodology, and summary statistics are written to
[`anomalies.json`](anomalies.json).

### 2. News ingestion and persistence

[`news/ingest.py`](news/ingest.py) retrieves company news from Finnhub
for the selected anomaly windows.

Articles are normalized and persisted by
[`news/store.py`](news/store.py) in:

``` text
data/news.sqlite
```

The store provides:

-   ticker normalization,
-   canonicalized URLs,
-   SHA-256 article IDs,
-   idempotent insertion,
-   publication timestamps normalized to UTC,
-   per-day ingestion state,
-   time-bounded retrieval,
-   SQLite FTS5 search when available.

Malformed provider records are skipped rather than reconstructed.

### 3. Retrieval and retrieval scoring

[`news/ranker.py`](news/ranker.py) assigns an explainable heuristic
score used to select potentially useful news.

The ranking considers signals including:

-   company/ticker relevance,
-   event-related terminology,
-   same-day or recent publication,
-   event specificity,
-   commentary-style headlines,
-   multi-story articles.

This is a **retrieval score**. It measures usefulness for evidence
selection under the implemented heuristic.

It is **not an estimate of the probability that an article caused a
market movement**.

Similar headlines can be deduplicated before investigation.

### 4. News grouping

[`news/event_grouping.py`](news/event_grouping.py) groups retrieved
articles using a precision-oriented heuristic based on event
characteristics such as event type, counterparties, status, details, and
textual overlap.

Grouping occurs before LLM investigation so that related articles can be
reviewed as event-oriented evidence rather than treated only as
unrelated search results.

### 5. LLM investigation

[`news/investigate.py`](news/investigate.py) reviews selected news
groups.

The implementation makes **one independent LLM request per selected
event group** and requests structured JSON rather than unrestricted
narrative output.

A supported hypothesis can contain:

``` text
event
mechanism
evidence_id
evidence_quote
relationship_class
```

The investigation distinguishes documented events from market causality.
A plausible economic mechanism is not treated as proof that the event
caused the anomaly.

Candidate relationship classes include states such as:

``` text
documented_market_link
plausible_unverified_link
needs_review
no_supported_link
```

Investigation results can also be classified as context-only,
insufficient evidence, rejected by validation, or supported hypotheses
depending on the evidence and validation outcome.

### 6. Semantic assessment and candidate scoring

For supported hypotheses, the investigation can provide six normalized
semantic assessments:

-   relationship directness,
-   economic plausibility,
-   materiality,
-   directional consistency,
-   novelty,
-   market-footprint fit.

Each model-assessed criterion includes a value, rationale, and
supporting evidence quote. Missing or invalid criteria remain missing
rather than being fabricated.

The deterministic scoring implementation in
[`news/causal_scoring/scorer.py`](news/causal_scoring/scorer.py)
combines those assessments with rule-derived evidence criteria
including:

-   temporal fit,
-   source independence,
-   primary-source support,
-   contradiction strength.

The default scoring weights are:

  Criterion                   Weight
  ------------------------- --------
  Temporal fit                  0.18
  Relationship directness       0.14
  Economic plausibility         0.14
  Materiality                   0.12
  Directional consistency       0.10
  Market-footprint fit          0.10
  Source independence           0.08
  Primary-source support        0.08
  Novelty                       0.06

The deterministic scorer also applies evidence-coverage requirements,
core-criterion checks, contradiction penalties, score caps, and
classification thresholds.

The resulting score is an **uncalibrated candidate-ranking score from
0--100**. It is not a causal probability.

## Scoring and Evidence

The system intentionally maintains separate concepts that should not be
interpreted interchangeably.

### Retrieval score

Produced by the news ranker.

It answers approximately:

> How useful does this article appear for investigating this anomaly
> under the retrieval heuristic?

It is used for news selection and ordering.

### Candidate assessment score

Produced after a supported hypothesis has been extracted and semantic
criteria have been assessed.

It combines model-supplied semantic judgments with deterministic
criteria and policies.

Depending on evidence coverage and score, the deterministic layer can
classify a candidate as:

``` text
ineligible
insufficient_evidence
weak
plausible
strong_candidate
```

These classifications describe the scoring policy's treatment of a
**candidate explanation**. They do not establish causation.

### Evidence coverage

Coverage is based on the configured criterion weights for which usable
values exist.

Insufficient coverage can cap the candidate score and produce an
`insufficient_evidence` classification.

### Evidence IDs

News records receive stable SHA-256 IDs when stored.

Evidence IDs are propagated through investigation and scoring so that:

``` text
article
→ extracted event
→ supporting quote
→ semantic assessment
→ candidate score
→ event-level result
```

can be audited.

### Claim flags and review status

The investigation contains deterministic checks around model-generated
claims and evidence excerpts.

Potential problems are retained as review flags rather than silently
converted into verified claims.

The final ranking marks assessments as `review_required` when conditions
such as claim flags, missing/ineligible scoring results, or
review-required relationships are present.

A candidate with complete scoring information remains
`scored_unverified`; this does **not** mean independently verified.

### Multiple articles for the same event

[`news/final_ranking.py`](news/final_ranking.py) performs conservative
offline grouping of already-scored hypotheses.

The current event-identity logic is deliberately narrow. In the current
implementation it explicitly normalizes equivalent quarterly
delivery-miss descriptions such as `Q1` and `first-quarter` before
grouping.

When multiple assessments belong to one grouped event, the system does
**not** average them into a new causal score.

Instead it selects a representative assessment by preferring:

1.  candidates without automated review flags,
2.  greater evidence coverage,
3.  higher candidate score,
4.  retrieval score as a tie-breaker.

Other assessments remain attached to the event for audit.

If any grouped assessment contains review reasons, the event-level
status is conservatively propagated as `review_required`.

The number of grouped articles is also **not interpreted as the number
of independent sources**.

## Audit-First Design

The project is intentionally conservative about what can be concluded
from news and daily market data.

Several safeguards are implemented:

-   Python-computed market data is treated as the source of truth for
    anomaly statistics.
-   The reporting agent is instructed not to invent financial data or
    news.
-   Generated market reports are checked by a deterministic validator.
-   News text is explicitly treated as untrusted source data rather than
    instructions.
-   LLM evidence quotes are checked against the underlying article text.
-   Claim-level issues can be preserved as review flags.
-   Missing semantic criteria are not automatically invented.
-   Scoring policy and criterion provenance are retained in structured
    output.
-   Article lineage is not inferred merely because several articles
    exist.
-   Final event grouping does not recompute a pooled score from
    duplicate evidence.
-   Existing scoring sidecars are checked for freshness before final
    ranking is generated.
-   Evidence graphs are generated offline and do not create new causal
    scores or rankings.
-   Clean reports explicitly label causality as unverified.

This separation allows the system to say:

> A documented event is a plausible candidate explanation.

without silently changing that into:

> This event caused the stock move.

## Evidence Graphs

[`news/evidence_graph.py`](news/evidence_graph.py) builds an offline
provenance-oriented evidence map for individual anomaly dates.

The graph links anomaly observations, retrieved news groups, articles,
and available semantic annotations while preserving provenance.

The graph implementation explicitly records that:

-   edges are non-causal,
-   intraday price onset is unknown,
-   source-lineage independence is not verified,
-   text matching does not prove semantic entailment,
-   no new graph-assisted economic score is produced,
-   no graph-based reranking is performed,
-   no model calls are made during graph construction.

Evidence graphs therefore serve as an **audit and provenance
representation**, not as a causal inference engine.

## Key Engineering Techniques

### Deterministic financial anomaly detection

Market anomalies are calculated in Python rather than inferred by the
LLM. The detector combines lagged rolling volume statistics with an
absolute-return threshold.

### Tool-calling agent workflow

The main financial agent exposes `analyze_ticker` as a LangChain tool.
The model chooses the tool, Python performs the market analysis, and the
resulting structured data becomes the basis for report generation.

### Structured LLM investigation

News groups are investigated independently and expected to return
constrained JSON containing status, reasoning, hypothesis information,
evidence references, and optional semantic assessments.

### Separation of model judgment and deterministic scoring

The LLM can assess semantic properties of a candidate, but deterministic
Python code owns weighting, temporal cutoffs, source-lineage handling,
contradiction penalties, evidence coverage, score caps, and final
candidate classification.

### Evidence-linked scoring

Each semantic criterion can reference the evidence item used to support
it. Pydantic models validate evidence references and reject unknown
evidence IDs.

### Local retrieval layer

News is ingested once into SQLite and later retrieved from the local
store using strict publication-time bounds. SQLite FTS5 is used when
available.

### Conservative event grouping

Retrieved articles can be grouped before investigation, while
already-scored hypotheses undergo a separate conservative grouping step
for final presentation.

### Deterministic validation

The market-report validator checks anomaly counts and reported event
values against the Python-generated source JSON and flags unsupported
interpretation patterns.

### Stale-output protection

[`run.py`](run.py) records modification times before execution and only
continues the news pipeline from a report generated by the current run.

It also checks that the scoring sidecar was freshly generated before
constructing the final ranking.

### Reproducible offline post-processing

Final event grouping/ranking and evidence-graph construction operate on
persisted artifacts without requiring additional LLM inference.

## Technology Stack

  ----------------------------------------------------------------------------------------
  Component                           Implementation
  ----------------------------------- ----------------------------------------------------
  Language                            Python

  Market data                         [yfinance](https://github.com/ranaroussi/yfinance)

  Data processing                     [pandas](https://pandas.pydata.org/) /
                                      [NumPy](https://numpy.org/)

  Agent/tool interface                [LangChain](https://python.langchain.com/)

  Active LLM client                   `langchain-openai` against a local OpenAI-compatible
                                      endpoint

  Active configured model             NVIDIA Nemotron 3.5 Lightning

  Additional local model              Ollama / Nemotron 3 Nano / Qwen3
  configurations                      

  News provider                       [Finnhub](https://finnhub.io/) company-news API

  Persistence                         Python `sqlite3` / SQLite, optionally FTS5

  Structured scoring contracts        [Pydantic v2](https://docs.pydantic.dev/latest/)

  Evidence/report format              JSON, Markdown, plain text
  ----------------------------------------------------------------------------------------

The active model in [`model.py`](model.py) points to:

``` text
http://localhost:8003/v1
```

through an OpenAI-compatible interface. Two Ollama-backed model
configurations are also defined in the same file but are not assigned to
the active `llm` variable.

## Project Structure

``` text
.
├── run.py                         # End-to-end entry point
├── agent_runner.py                # Tool-calling market-analysis agent
├── model.py                       # LLM and tool configuration
├── tools.py                       # analyze_ticker LangChain tool
├── anomalies.json                 # Latest structured anomaly output
├── report.txt                     # Validated market-analysis report
├── report_draft.txt               # Report retained when validation fails
├── requirements.txt
│
├── utils/
│   ├── market_analysis.py         # Market download + anomaly calculation
│   └── report_validator.py        # Deterministic report checks
│
├── news/
│   ├── ingest.py                  # Finnhub ingestion
│   ├── store.py                   # SQLite persistence and retrieval
│   ├── retrieve.py                # Time-bounded evidence retrieval
│   ├── ranker.py                  # Heuristic retrieval scoring
│   ├── event_grouping.py          # Article/event grouping
│   ├── selection.py               # Deterministic anomaly selection
│   ├── investigate.py             # Per-group LLM investigation
│   ├── final_ranking.py           # Offline event grouping/ranking
│   ├── evidence_graph.py          # Offline provenance/evidence graph
│   ├── report_evidence.py         # Evidence appendix generation
│   ├── clean_report.py            # Final readable audit report
│   │
│   └── causal_scoring/
│       ├── models.py              # Pydantic evidence/scoring contracts
│       ├── adapter.py             # Investigation → scoring adapter
│       ├── scorer.py              # Deterministic candidate scorer
│       ├── enrich.py
│       └── ranker.py
│
├── data/
│   └── news.sqlite                # Local news database
│
├── evidence/
│   ├── news_investigation.txt
│   ├── news_investigation.txt.scores.json
│   ├── final_ranking.json
│   ├── final_ranking.md
│   ├── evidence_graph_*.json
│   ├── evidence_graph_*.md
│   ├── report_with_evidence_*.md
│   ├── report_with_evidence.md
│   └── report_clean.md            # Consolidated readable report
│
└── tests/
    └── test_*.py
```

`utils/` contains the core deterministic market-analysis and validation
logic.

`news/` contains the news-specific ingestion, retrieval, investigation,
scoring, evidence, and reporting pipeline.

`news/causal_scoring/` separates typed evidence contracts and
deterministic score aggregation from LLM investigation.

`data/` contains runtime persistence.

`evidence/` contains generated investigation, scoring, graph, ranking,
audit, and reporting artifacts rather than application source code.

## Configuration

Finnhub ingestion requires the following environment variable:

``` bash
export FINNHUB_API_KEY="..."
```

The key is read at runtime by [`news/ingest.py`](news/ingest.py). API
keys should not be committed to source code.

The current LLM configuration expects an OpenAI-compatible local
endpoint at:

``` text
http://localhost:8003/v1
```

The repository also contains Ollama model configurations pointing to:

``` text
http://localhost:11434
```

Model serving itself is external to this repository.

## Generated Outputs

### `anomalies.json`

Structured output from deterministic market analysis. It contains the
anomaly methodology, summary statistics, and anomaly events used by
downstream stages.

### `report.txt` / `report_draft.txt`

The market-analysis report generated from `anomalies.json`.

A validated report is written to `report.txt`; an unvalidated result can
be retained separately as `report_draft.txt`.

### `evidence/news_investigation.txt`

Human-readable audit output from per-group LLM news investigation,
including source records, investigation statuses, evidence references,
and review information.

### `evidence/news_investigation.txt.scores.json`

Structured scoring sidecar for supported hypotheses.

It preserves candidate hypotheses, semantic assessments, deterministic
score results, scoring-policy details, evidence coverage, missing
criteria, and limitations.

### `evidence/final_ranking.json`

Offline event-level representation built from already-scored hypotheses.

It contains the representative candidate score, event status, grouped
evidence IDs, candidate-level audit records, and explicit limitations.

### `evidence/evidence_graph_*.json`

Per-anomaly provenance graphs connecting the market anomaly with
retrieved evidence.

These graphs do not provide causal edges or new graph-derived scores.

Corresponding Markdown renderings are generated as
`evidence_graph_*.md`.

### `evidence/report_with_evidence*.md`

Audit-oriented reports combining market analysis with descriptive
evidence appendices.

### `evidence/report_clean.md`

The consolidated presentation report.

It combines the anomaly date and market movement, retrieval overview,
grouped event result, representative event score, review status,
supporting article assessments, evidence excerpts, and audit references.