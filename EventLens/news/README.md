# News pipeline — architecture, formulas, evidence and limitations

> **Source of truth:** the user's original `mvp2(1).zip` (not any previous assistant refactor). This document describes the code in that archive. The optional lightweight assessment export supplied alongside this README is presentation-only; it does **not** introduce a new numerical causal score.

## 1. What problem does this solve?

The market agent detects unusual daily price/volume observations and writes `anomalies.json`. The news subsystem looks for **possible contemporaneous context** using Finnhub company-news metadata and summaries. It does not prove what caused a price move. Its stages are ingestion → local SQLite → retrieval and article ranking → event grouping → group selection → independent LLM review → deterministic claim validation → evidence graph and readable report. The original market agent, its anomaly formula and its report validator are separate components; see the root README and `tools.py` for their authoritative implementation.

**Three different concepts must not be confused:** (a) *retrieval score* ranks which articles to read; (b) *investigation status* says what the model and validator found; (c) *causal-candidate score* is an optional, more demanding module that is **not called by the original `run.py`**. A retrieval score of 0.9 is not a 90% probability of causality.

## 2. Entrypoint and data flow

`run.py` calls `run_agent(...)` first. It continues only if `report.txt` or `report_draft.txt` was newly written in the current invocation. A draft is visibly labelled `UNVALIDATED DRAFT`. `--no-news` stops after the market agent; `--no-investigation` skips model calls. News errors are caught without overwriting the main report. The news phase reads `anomalies.json`, selects events **once**, then passes the identical subset to ingestion and investigation. It produces per-day evidence graphs and both raw and readable reports in `evidence/`.

**Demo selection (`news/selection.py`):** eligible events are dated between `today - 365 days` and today, inclusive. Sort deterministically, then use `random.Random(seed=42).sample(..., min(3, eligible_count))`, finally sort selected events by date. `--no-demo` processes all events. This is a seeded *sample*, not the three most extreme anomalies.

## 3. Ingestion and provenance (`news/ingest.py`, `news/store.py`)

`ingest_anomaly_windows` fetches Finnhub company news for the selected anomaly windows, includes the event day when called from `run.py`, and stores article metadata/title/summary in `data/news.sqlite`. The fetcher requires `FINNHUB_API_KEY` from the environment; never commit credentials. It validates provider responses, handles HTTP 429 with bounded retries, and marks a day complete **after** storing the articles. A failed day causes `run.py` to skip investigation and graphs rather than silently present partial coverage. Cached articles avoid treating every execution as a fresh research source. News is retrieved from the **local database** for investigation; the ingestion phase itself does access Finnhub over the network. The source URLs in the database are references, not proof that the full article body was downloaded.

## 4. Evidence time window and its limits (`news/investigate.py`)

For anomaly date `D`, start is midnight New York time on `D - days` (default `days=7`); end is 16:00 New York time on `D`, inclusive. Both timestamps are converted to timezone-aware UTC for SQLite filtering. Query: ticker matches, `published_at >= start`, `published_at <= cutoff`, ordered newest first, `LIMIT 5000`. Daily OHLCV **cannot reveal when within the day the anomalous move began**. Publication before the regular close only establishes that news was available by close, not that it preceded the move. After-close articles are excluded from this investigation window. The separate `retrieve_for_anomaly()` helper in `news/retrieve.py` uses a more conservative *previous-day-only UTC cutoff*; do not confuse that helper with the live investigation path.

## 5. Article retrieval score (`news/ranker.py`)

The deterministic `score_article` heuristic uses title and summary. `R` (company relevance) is 1 for ticker/company alias in title, 0.6 for summary-only, otherwise 0. `E` (event strength) is 1 for an event keyword in title, 0.35 for a category keyword elsewhere, otherwise 0. `S` (specificity) is 1 for a direct title match plus title event and not multi-story, 0.3 for a direct non-multi-story match without title event, otherwise 0. `Q` is a **format proxy**, 0 for multi-story and 1 otherwise; **it is not publisher trustworthiness**. `C` is 1 for commentary-title phrases, otherwise 0.

Let `h = max(0, hours between article publication and the event cutoff)` and `F = max(0, 1 - h/168)`. `D = 1` if publication date in New York equals anomaly date, otherwise 0. Then:

```text
raw = 0.25*R + 0.25*E + 0.15*(1 if D else 0.5*F)
    + 0.05*F + 0.20*S + 0.10*Q - 0.25*C
retrieval_score = round(min(1, max(0, raw)), 4)
```

Only articles explicitly mentioning the company/ticker in title or summary survive the `company_mentioned` filter. Sort by descending score, then newest publication, then ID. The default `rank_articles` function can deduplicate near-identical normalized titles when similarity via `SequenceMatcher >= 0.90`; **the investigation calls it with `deduplicate=False` and groups all matching candidates before selecting evidence slots**. A `company_name` absent from the anomaly payload means name-only stories may be missed. This score ranks article relevance, **not the model's causal conclusion**.

## 6. Event grouping (`news/event_grouping.py`)

The system derives each article's signature from its title: event types (investment, partnership, approval, restriction, earnings), distinctive words after stopword removal, explicitly formatted financial numbers, and event status (negative, pending, confirmed, unspecified). `related(a,b)` requires compatible status (unless unspecified), compatible event types when both exist, matching financial numbers when both exist, timestamps no more than 72 hours apart *when parseable*, and at least one shared distinctive token. Ordinarily at least **two** distinctive tokens must overlap; a matching financial number relaxes this requirement. Finally:

```text
Jaccard_title = |words(title_a) ∩ words(title_b)| / max(1, |words(title_a) ∪ words(title_b)|)
related = Jaccard_title >= 0.32
          OR (shared_distinctive_words >= 3 AND event_types_overlap)
```

The earlier compatibility gates still apply. Greedy `group_articles` places a candidate into the **first** group for which it is related to **every existing member**; otherwise it creates a new group. This is not embedding clustering or a transitive connected-component algorithm. Groups are ranked by their **maximum member retrieval score**. The representative is the highest-ranked member, breaking ties with specificity and publication timestamp. Group size is **not** a count of independent publishers or independent reporting lineages.

## 7. Which groups reach the model? (`news/investigate.py`)

`MAX_EVIDENCE=12` groups per anomaly. The selector reserves up to two slots for macro/sector candidates, but these must still mention the company and match predefined macro plus market keywords. Remaining slots balance same-day and older groups, then fill leftover slots in ranking order. Final chosen groups are sorted by their maximum article score. This is a coverage heuristic; the model does **not** review every stored article. The investigation text reports stored article count, lexically relevant count, selected groups, same-day/older group counts and macro counts.

## 8. LLM investigation and deterministic validation (`news/investigate.py`)

One independent `llm.invoke` call per selected group uses the representative article's **title and summary** as untrusted evidence. The prompt requests JSON with `status`, `reason` and at most one hypothesis. The model must quote an exact contiguous passage and distinguish documented events, conditional mechanisms and causal proof. Statuses: `supported_hypothesis`, `context_only`, `insufficient_evidence`; transport/model failures become `llm_error`. Invalid JSON/schema, invalid quote/claim, conflicting-direction claims without a market bridge, and other guardrail failures can become `validation_rejected`.

`_validate_detailed` verifies structured fields, cited article ID, quotes and other claim guards; it is a **lexical/contract check, not independent fact-checking or semantic entailment proof**. The pipeline records `claim_flags`, relationship class (`documented_market_link`, `plausible_unverified_link`, `needs_review`, `no_supported_link`), event status and direction alignment. A validated hypothesis is a *plausible contextual candidate*, not an established cause. The raw text includes rejected-hypothesis audits, model-call counts, elapsed time and token usage when supplied by the model.

## 9. Evidence graph and outputs

`news/evidence_graph.py` and `news/report_evidence.py` create descriptive evidence maps and appendices, not new scores. The graph contract explicitly requires `graph_ranks_computed == 0` and no new rank/graph-assisted score. `news/clean_report.py` parses the investigation text and joins model assessments to source records by the **original article/group ID**. It displays the existing retrieval rank and the model's separate assessment. Original outputs include:

| Output | Purpose |
|---|---|
| `anomalies.json` | Market events from the original agent |
| `data/news.sqlite` | Cached company-news metadata and summaries |
| `evidence/news_investigation.txt` | Raw per-group LLM/validator audit and source records |
| `evidence/report_clean.md` | Human-readable ranked news, links and interpretations |
| `evidence/report_with_evidence.md` | Main report + raw investigation + evidence appendices |
| `evidence/evidence_graph_<DATE>.json/.md` | Descriptive graph for each selected day |
| `evidence/report_with_evidence_<DATE>.md` | Individual daily appendix |

The optional `evidence/hypothesis_scoring_readiness.json` added by this patch is **an audit of whether hypotheses have enough explicit data to score**, not a causal score.

## 10. The existing `causal_scoring/` module: implemented vs wired

The original archive contains `models.py`, `adapter.py`, `scorer.py`, `ranker.py`, `enrich.py`. The scorer implements a weighted heuristic with temporal fit (0.18), relationship directness (0.14), economic plausibility (0.14), materiality (0.12), directional consistency (0.10), source independence (0.08), primary-source support (0.08), novelty (0.06), market-footprint fit (0.10), and contradiction penalty 0.25. Its generic expression is `100 * max(0, weighted_base - 0.25 * contradiction_strength)`, with additional eligibility, missing-evidence and cap rules; read `scorer.py` for exact behavior. These numbers are **uncalibrated heuristic weights**, not probabilities.

**Critical:** original `run.py` never invokes this module. `adapter.py` expects explicit semantic values (0–1 plus rationale); missing ones become `None`. `enrich.py` can make additional LLM requests, but re-running a model increases latency and schema/quote failure risk. Neither a `supported_hypothesis` label nor a retrieval score supplies the six numeric semantic criteria. In particular, independent sources, novelty, materiality and peer-market footprint cannot be inferred safely from group size, headlines or daily return alone. This patch therefore **does not turn on `enrich.py`, does not manufacture 0.5 values, and does not publish misleading numeric scores**. Instead, it exports a deterministic readiness audit from already-produced investigation results; later scoring should require explicit, evidence-linked inputs and a versioned reduced-weight policy if criteria are removed.

## 11. Lightweight assessment export (optional, no new LLM calls)

`news/lightweight_scoring.py` reads the existing raw investigation, extracts anomaly date, source rank, group ID, review status, relationship class, direction and flags. It marks each group `rejected`, `not_supported`, `review_required`, or `candidate_unscored`. It deliberately leaves `causal_score: null` because the required semantic measurements were never produced. The export is transparent and avoids a second LLM pass; the original `run.py` and tests remain untouched. To generate it from existing output:

```bash
python -m news.lightweight_scoring --input evidence/news_investigation.txt --output evidence/hypothesis_scoring_readiness.json
```

If a future release supplies evidence-backed semantic criteria, connect the existing scorer behind a separate opt-in feature and verify score coverage, source lineage, temporal cutoff and policy version before publishing numbers.

## 12. Running the project

Run commands from the project root with its dependencies installed and your existing model endpoint configured. Set `FINNHUB_API_KEY` in the environment; do not add secrets to the repository. The entrypoint prompts for the market question.

```bash
python run.py                     # default: 3 seeded demo events; fetch + investigate
python run.py --no-demo           # all events (potentially many API/model calls)
python run.py --no-investigation  # skip investigation model calls
python run.py --no-news           # market agent only
python -m news.lightweight_scoring --input evidence/news_investigation.txt --output evidence/hypothesis_scoring_readiness.json
```

For quick validation: `python -m compileall -q news` and `python -m pytest -q tests/test_event_grouping.py tests/test_news.py` if dependencies are installed. Full integration requires Finnhub credentials and a working model. **Do not interpret offline compilation as proof of end-to-end success.**

## 13. Source–hypothesis alignment audit (optional patch v2)

The optional `lightweight_scoring.py` v2 adds **offline triage** of each extracted event against the representative source headline and the exact excerpt recorded by Investigation. It emits `source_alignment.status`, `title_matches`, `excerpt_matches`, and `review_reasons`. A multi-story article can legitimately mention Tesla in its body without putting Tesla in its headline: a headline mismatch triggers **human review**, never automatic rejection. Lexical overlap is **not** semantic verification, and the quoted excerpt still needs source/provenance checking. This specifically highlights the April 2 Blue Owl headline / Tesla deliveries hypothesis for review.

The output schema is `scoring-readiness-v2`. `causal_score` remains `null`: the original investigation does not supply evidence-backed numeric semantic criteria. No new LLM calls, database queries, formula changes, or edits to `run.py` are made. Use the command in section 11 to regenerate the JSON; existing `scoring-readiness-v1` files are not automatically migrated. This is an **audit step, not a completed numerical scoring integration**.
