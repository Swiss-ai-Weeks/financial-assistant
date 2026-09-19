from __future__ import annotations

import argparse

from collections import Counter
from concurrent.futures import (
    ThreadPoolExecutor,
)

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path
from time import perf_counter

import pandas as pd

from financial_assistant.anomaly_detection import (
    pair_anomaly_to_event,
)

from financial_assistant.anomaly_detection.historical import (
    HistoricalPairSignal,
    scan_pairs_as_of,
)

from financial_assistant.claimgraph.builder_v2 import (
    build_investigation_graph,
)

from financial_assistant.domain import (
    InvestigationState,
)

from financial_assistant.llm import (
    OpenAICompatibleProvider,
    assess_relationships,
    audit_hypotheses,
    extract_claims,
    generate_hypotheses,
)

from financial_assistant.research.planner import (
    plan_research,
)

from financial_assistant.retrieval import (
    RetrievalStatus,
    SearxngSearchProvider,
    TrafilaturaDocumentFetcher,
    execute_research_plan,
)


from financial_assistant.retrieval import (
    CorpusDocumentFetcher,
    CorpusSearchProvider,
    SearxngSearchProvider,
    TrafilaturaDocumentFetcher,
)

from financial_assistant.retrieval.composite import (
    CompositeSearchProvider,
    DispatchingDocumentFetcher,
)

from financial_assistant.retrieval.bookreader import (
    CorpusDocumentFetcher,
    CorpusSearchProvider,
)

from financial_assistant.retrieval.composite import (
    CompositeSearchProvider,
    DispatchingDocumentFetcher,
)

from financial_assistant.simulation import (
    simulate_pair_forward,
)


timings: dict[str, float] = {}


def timed(name, func):
    started = perf_counter()

    result = func()

    timings[name] = (
        perf_counter()
        - started
    )

    return result


def parse_aware_datetime(
    value: str,
) -> datetime:
    parsed = datetime.fromisoformat(
        value.replace(
            "Z",
            "+00:00",
        )
    )

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            "--observed-at must include "
            "a timezone offset."
        )

    return parsed


def find_signal(
    prices: pd.DataFrame,
    *,
    as_of: str,
    ticker_a: str,
    ticker_b: str,
) -> HistoricalPairSignal:
    signals = scan_pairs_as_of(
        prices,

        as_of=as_of,

        formation_observations=252,

        corr_min=0.70,
        alpha=0.01,
        entry=2.0,
    )

    target = {
        ticker_a.upper(),
        ticker_b.upper(),
    }

    for signal in signals:
        pair = {
            signal.fit.ticker_a,
            signal.fit.ticker_b,
        }

        if pair == target:
            return signal

    available = [
        (
            signal.fit.ticker_a,
            signal.fit.ticker_b,
            signal.anomaly.z_score,
        )
        for signal in signals
    ]

    raise RuntimeError(
        "Requested pair was not anomalous "
        f"on {as_of}.\n"
        f"Available anomalies: {available}"
    )


def select_historical_documents(
    bundle,
    plan,
    *,
    limit: int,
):
    """
    Select only documents whose publication timestamp
    is KNOWN and at/before the historical cutoff.

    Undated documents remain in RetrievalBundle as
    execution provenance, but they are not allowed into
    historical claim extraction.
    """

    task_priority = {
        task.task_id:
            task.priority
        for task in plan.tasks
    }

    document_priority: dict[
        str,
        int,
    ] = {}

    for record in bundle.records:
        if record.document_id is None:
            continue

        priority = task_priority.get(
            record.task_id,
            5,
        )

        existing = (
            document_priority.get(
                record.document_id,
                5,
            )
        )

        document_priority[
            record.document_id
        ] = min(
            existing,
            priority,
        )

    eligible = [
        document
        for document in bundle.documents
        if (
            document.published_at
            is not None

            and (
                (
                    document.published_date_only
                    and (
                        document
                        .published_at
                        .date()
                        < plan.as_of.date()
                    )
                )
                or (
                    not document.published_date_only
                    and (
                        document.published_at
                        <= plan.as_of
                    )
                )
            )
        )
    ]

    # Higher-priority research tasks first, then
    # evidence nearest to the historical cutoff.
    eligible.sort(
        key=lambda document: (
            document_priority.get(
                document.document_id,
                5,
            ),

            -document
            .published_at
            .timestamp(),

            document.title,
        )
    )

    return tuple(
        eligible[:limit]
    )


def extract_document_claims(
    documents,
    provider,
):
    """
    Claim extraction is independent by document.

    Run the calls concurrently so vLLM can batch them,
    while executor.map preserves document ordering.
    """

    def extract_one(document):
        try:
            run, claims = extract_claims(
                document,
                provider,
                max_document_chars=6000,
            )

            return (
                document,
                run,
                claims,
                None,
            )

        except Exception as exc:
            return (
                document,
                None,
                (),
                exc,
            )

    if not documents:
        return ()

    workers = min(
        4,
        len(documents),
    )

    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix=(
            "claimgraph-claims"
        ),
    ) as executor:
        return tuple(
            executor.map(
                extract_one,
                documents,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prices",
        default=(
            "data/cache/market/"
            "demo_us_daily.csv"
        ),
    )

    parser.add_argument(
        "--as-of",
        default="2026-02-27",
    )

    parser.add_argument(
        "--ticker-a",
        default="AXP",
    )

    parser.add_argument(
        "--ticker-b",
        default="BAC",
    )

    parser.add_argument(
        "--observed-at",
        default=(
            "2026-02-27T21:00:00+00:00"
        ),
    )

    parser.add_argument(
        "--per-task-limit",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--max-documents",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--claims-per-document",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--max-claims",
        type=int,
        default=8,
    )

    args = parser.parse_args()

    prices = pd.read_csv(
        args.prices
    )

    ticker_a = (
        args.ticker_a
        .strip()
        .upper()
    )

    ticker_b = (
        args.ticker_b
        .strip()
        .upper()
    )

    observed_at = (
        parse_aware_datetime(
            args.observed_at
        )
    )

    print()
    print(
        "HISTORICAL INVESTIGATION"
    )

    print(
        "=" * 60
    )

    # -------------------------------------------------
    # 1. Reconstruct quantitative signal.
    # -------------------------------------------------

    signal = timed(
        "historical_scan",
        lambda: find_signal(
            prices,
            as_of=args.as_of,
            ticker_a=ticker_a,
            ticker_b=ticker_b,
        ),
    )

    anomaly = signal.anomaly
    fit = signal.fit

    print()
    print(
        "PAIR:",
        f"{fit.ticker_a}/{fit.ticker_b}",
    )

    print(
        "SIGNAL DATE:",
        signal.as_of,
    )

    print(
        "OBSERVED AT:",
        observed_at.isoformat(),
    )

    print(
        "Z SCORE:",
        f"{anomaly.z_score:+.3f}",
    )

    print(
        "CORRELATION:",
        f"{fit.correlation:.3f}",
    )

    print(
        "COINTEGRATION P:",
        f"{fit.pvalue:.5f}",
    )

    print(
        "BETA:",
        f"{fit.beta:.3f}",
    )

    print(
        "FORMATION:",
        fit.formation_start,
        "→",
        fit.formation_end,
    )

    # -------------------------------------------------
    # 2. Convert quant observation into ClaimGraph's
    #    neutral attention-event contract.
    # -------------------------------------------------

    event = pair_anomaly_to_event(
        anomaly,
        observed_at=observed_at,
    )

    # -------------------------------------------------
    # 3. Deterministic historical research plan.
    # -------------------------------------------------

    plan = plan_research(
        event
    )

    print()
    print(
        "RESEARCH CUTOFF:",
        plan.as_of.isoformat(),
    )

    print(
        "RESEARCH TASKS:",
        len(plan.tasks),
    )

    for task in plan.tasks:
        print(
            " ",
            task.priority,
            task.kind.value,
            task.entities,
        )

    # -------------------------------------------------
    # 4. Execute retrieval.
    #
    # retrieved_at is NOW because this records when
    # this reconstruction was actually executed.
    #
    # plan.as_of is THEN and determines which evidence
    # is historically admissible.
    # -------------------------------------------------

    retrieved_at = datetime.now(
        timezone.utc
    )


    search_provider = CompositeSearchProvider(
    providers=(
        # Controlled evidence universe first.
        CorpusSearchProvider(
            lookback_days=45,
        ),

        # Then augment with open-web discovery.
        SearxngSearchProvider(),
    ))

    document_fetcher = DispatchingDocumentFetcher(
            fetchers={
                "bookreader": (
                    CorpusDocumentFetcher()
                    ),
                "searxng": (
                    TrafilaturaDocumentFetcher()
                    ),
                }
            )

	
	print()

	print(
    	"RETRIEVAL SOURCES:",
    	"BookReader corpus + SearXNG web",
	)

	print(
    	"BOOKREADER CORPUS:",
    	"Financial Times + Wall Street Journal",
	)

	print(
    	"BOOKREADER LOOKBACK:",
    	"45 calendar days",
	)
	

    bundle = timed(
        "retrieval",
        lambda: execute_research_plan(
            plan,

            search_provider=(
                search_provider
            ),

            document_fetcher=(
                document_fetcher
            ),

            retrieved_at=(
                retrieved_at
            ),

            per_task_limit=(
                args.per_task_limit
            ),
        ),
    )

    status_counts = Counter(
        record.status.value
        for record in bundle.records
    )

    print()
    print(
        "RETRIEVAL EXECUTED AT:",
        retrieved_at.isoformat(),
    )

    print(
        "SEARCH HITS:",
        len(bundle.hits),
    )

    for status in RetrievalStatus:
        print(
            f"{status.value:18}",
            status_counts.get(
                status.value,
                0,
            ),
        )

    # -------------------------------------------------
    # 5. Strict historical evidence eligibility.
    # -------------------------------------------------

    documents = (
        select_historical_documents(
            bundle,
            plan,

            limit=(
                args.max_documents
            ),
        )
    )

    print()
    print(
        "DATED HISTORICAL DOCUMENTS USED:",
        len(documents),
    )

    for index, document in enumerate(
        documents,
        start=1,
    ):
        print()
        print(
            f"DOC {index}:",
            document.title,
        )

        print(
            "  publisher:",
            document.publisher,
        )

        print(
            "  published:",
            (
                document
                .published_at
                .isoformat()
            ),
        )

        print(
            "  url:",
            document.url,
        )

    if not documents:
        raise RuntimeError(
            "No historically admissible dated "
            "documents were retrieved. "
            "Inspect RetrievalBundle before "
            "loosening any evidential rule."
        )

    # -------------------------------------------------
    # 6. NVIDIA NIM.
    # -------------------------------------------------

    provider = OpenAICompatibleProvider(
        provider_name="nvidia-nim",

        model_name=(
            "nvidia/"
            "llama-3.3-nemotron-super-49b-v1.5"
        ),

        base_url=(
            "http://127.0.0.1:8000/v1"
        ),

        max_tokens=2048,
    )

    # -------------------------------------------------
    # 7. Source-grounded claim extraction.
    # -------------------------------------------------

    extraction_results = timed(
        "claim_extraction",
        lambda: extract_document_claims(
            documents,
            provider,
        ),
    )

    claim_runs = []
    selected_claims = []
    seen_claim_text = set()

    document_by_id = {
        document.document_id:
            document
        for document in documents
    }

    for (
        document,
        run,
        document_claims,
        error,
    ) in extraction_results:

        if error is not None:
            print()
            print(
                "CLAIM EXTRACTION FAILED:",
                document.title,
            )

            print(
                " ",
                type(error).__name__,
                error,
            )

            continue

        claim_runs.append(
            run
        )

        added_from_document = 0

        for claim in document_claims:
            normalized = (
                " ".join(
                    claim.text
                    .lower()
                    .split()
                )
            )

            if normalized in seen_claim_text:
                continue

            seen_claim_text.add(
                normalized
            )

            selected_claims.append(
                claim
            )

            added_from_document += 1

            if (
                added_from_document
                >= args.claims_per_document
            ):
                break

            if (
                len(selected_claims)
                >= args.max_claims
            ):
                break

        if (
            len(selected_claims)
            >= args.max_claims
        ):
            break

    claims = tuple(
        selected_claims
    )

    if not claims:
        raise RuntimeError(
            "No validated source-grounded claims "
            "were extracted."
        )

    print()
    print(
        "SELECTED CLAIMS:",
        len(claims),
    )

    for claim in claims:
        source = document_by_id.get(
            claim.document_id
        )

        print()
        print(
            "CLAIM:",
            claim.claim_type.value,
            "|",
            claim.text,
        )

        if source is not None:
            print(
                "  source:",
                source.title,
            )

    # -------------------------------------------------
    # 8. Competing explanations.
    # -------------------------------------------------

    hypothesis_run, hypotheses = timed(
        "hypothesis_generation",
        lambda: generate_hypotheses(
            event,
            claims,
            provider,
        ),
    )

    # The dedicated audit stage owns assumptions.
    hypotheses = tuple(
        hypothesis.model_copy(
            update={
                "assumptions": (),
            }
        )
        for hypothesis in hypotheses
    )

    print()
    print(
        "HYPOTHESES:",
        len(hypotheses),
    )

    for hypothesis in hypotheses:
        print(
            " ",
            hypothesis.hypothesis_id,
            "|",
            hypothesis.text,
        )

    # -------------------------------------------------
    # 9. Premise / evidence-gap audit.
    # -------------------------------------------------

    audit_run, audits = timed(
        "hypothesis_audit",
        lambda: audit_hypotheses(
            event,
            claims,
            hypotheses,
            provider,
        ),
    )

    print(
        "HYPOTHESIS AUDITS:",
        len(audits),
    )

    # -------------------------------------------------
    # 10. Claim ↔ hypothesis assessments.
    # -------------------------------------------------

    relation_runs, assessments = timed(
        "relationship_assessment",
        lambda: assess_relationships(
            claims,
            hypotheses,
            provider,
            max_workers=4,
        ),
    )

    print(
        "RELATIONSHIP RUNS:",
        len(relation_runs),
    )

    print(
        "RELATIONSHIPS:",
        len(assessments),
    )

    # -------------------------------------------------
    # 11. Semantic investigation state.
    # -------------------------------------------------

    state = InvestigationState(
        investigation_id=(
            "INV-"
            f"{fit.ticker_a}-"
            f"{fit.ticker_b}-"
            f"{signal.as_of.isoformat()}"
        ),

        anomaly=event,

        documents=documents,

        model_runs=(
            *claim_runs,
            hypothesis_run,
            audit_run,
            *relation_runs,
        ),

        claims=claims,

        hypotheses=hypotheses,

        hypothesis_audits=audits,

        relationship_assessments=(
            assessments
        ),

        evidence_requirements=(),
        observations=(),
        calculations=(),
        inferences=(),
    )

    # -------------------------------------------------
    # 12. ClaimGraph.
    # -------------------------------------------------

    graph = timed(
        "graph_build",
        lambda: build_investigation_graph(
            state
        ),
    )

    print()
    print(
        "GRAPH NODES:",
        len(graph.nodes),
    )

    print(
        "GRAPH EDGES:",
        len(graph.edges),
    )

    # -------------------------------------------------
    # 13. Hindsight-only forward simulation.
    # -------------------------------------------------

    simulation = timed(
        "forward_simulation",
        lambda: simulate_pair_forward(
            signal,
            prices,

            gross_capital=10_000,

            horizons=(
                1,
                5,
                10,
                20,
            ),
        ),
    )

    print()
    print(
        "HINDSIGHT OUTCOME"
    )

    print(
        "NOT AVAILABLE AT SIGNAL TIME"
    )

    print(
        "entry:",
        simulation.entry_date,
        simulation.entry_metric,
    )

    print(
        "direction:",
        simulation.strategy_direction,
    )

    for point in (
        simulation.forward_returns
    ):
        print(
            f"{point.horizon_observations:>2} sessions: "
            f"{point.return_pct:+7.2f}% "
            f"${point.pnl:+8.2f}"
        )

    print(
        "latest:",
        f"{simulation.return_to_latest_pct:+.2f}%",
    )

    print(
        "max drawdown:",
        f"{simulation.max_drawdown_pct:+.2f}%",
    )

    print(
        "reverted:",
        simulation.mean_reversion_date,
    )

    # -------------------------------------------------
    # 14. Persist separate provenance products.
    # -------------------------------------------------

    stem = (
        f"{fit.ticker_a.lower()}_"
        f"{fit.ticker_b.lower()}_"
        f"{signal.as_of.isoformat()}"
    )

    fixture_dir = Path(
        "data/fixtures"
    )

    frontend_dir = Path(
        "frontend/public"
    )

    fixture_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    frontend_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    graph_path = (
        fixture_dir
        / f"investigation_{stem}.json"
    )

    frontend_graph_path = (
        frontend_dir
        / f"investigation_{stem}.json"
    )

    retrieval_path = (
        fixture_dir
        / f"retrieval_{stem}.json"
    )

    simulation_path = (
        fixture_dir
        / f"simulation_{stem}.json"
    )

    graph_json = (
        graph.model_dump_json(
            indent=2
        )
        + "\n"
    )

    graph_path.write_text(
        graph_json
    )

    frontend_graph_path.write_text(
        graph_json
    )

    retrieval_path.write_text(
        bundle.model_dump_json(
            indent=2
        )
        + "\n"
    )

    simulation_path.write_text(
        simulation.model_dump_json(
            indent=2
        )
        + "\n"
    )

    print()
    print(
        "WROTE:",
        graph_path,
    )

    print(
        "WROTE:",
        frontend_graph_path,
    )

    print(
        "WROTE:",
        retrieval_path,
    )

    print(
        "WROTE:",
        simulation_path,
    )

    # -------------------------------------------------
    # 15. Timing.
    # -------------------------------------------------

    print()
    print(
        "TIMINGS"
    )

    for name, seconds in (
        timings.items()
    ):
        print(
            f"{name:28} "
            f"{seconds:7.2f}s"
        )

    print(
        f"{'measured total':28} "
        f"{sum(timings.values()):7.2f}s"
    )

    print()
    print(
        "TEMPORAL PROVENANCE NOTE:"
    )

    print(
        "This is a historical evidence reconstruction "
        "using current search infrastructure with a "
        "strict publication-date cutoff. It does not "
        "reproduce the exact search index or ranking "
        "that existed at the historical timestamp."
    )


if __name__ == "__main__":
    main()
