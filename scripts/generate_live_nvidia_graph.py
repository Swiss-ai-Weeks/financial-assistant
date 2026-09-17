from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from financial_assistant.claimgraph.builder_v2 import (
    build_investigation_graph,
)

from financial_assistant.domain import (
    AnomalyEvent,
    ClaimType,
    InvestigationState,
)

from financial_assistant.llm import (
    OpenAICompatibleProvider,
    assess_relationships,
    audit_hypotheses,
    extract_claims,
    generate_hypotheses,
)

from financial_assistant.retrieval import (
    TrafilaturaDocumentFetcher,
)

from financial_assistant.retrieval.models import (
    SearchHit,
)


URL = (
    "https://nvidianews.nvidia.com/news/"
    "nvidia-announces-financial-results-for-"
    "fourth-quarter-and-fiscal-2026"
)


def main() -> None:
    # -------------------------------------------------
    # 1. Source retrieval
    # -------------------------------------------------

    hit = SearchHit(
        hit_id="LIVE-NVIDIA-EARNINGS",
        task_id="LIVE-NVDA-EARNINGS",
        provider="known-source",
        query="direct known source",
        rank=1,
        title=(
            "NVIDIA Announces Financial Results for "
            "Fourth Quarter and Fiscal 2026"
        ),
        url=URL,
        snippet="",
        publisher="nvidianews.nvidia.com",
        published_at=None,
    )

    document = (
        TrafilaturaDocumentFetcher()
        .fetch(
            hit,
            retrieved_at=datetime.now(
                timezone.utc
            ),
        )
    )

    print(
        "SOURCE:",
        document.title,
    )


    # -------------------------------------------------
    # 2. NVIDIA NIM
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
    # 3. Claim extraction
    # -------------------------------------------------

    claim_run, extracted_claims = (
        extract_claims(
            document,
            provider,
            max_document_chars=6000,
        )
    )

    print(
        "EXTRACTED CLAIMS:",
        len(extracted_claims),
    )


    # Keep the visual experiment compact and diverse:
    # two reported facts, one forecast and one
    # attributed management claim.

    reported = [
        claim
        for claim in extracted_claims
        if (
            claim.claim_type
            == ClaimType.REPORTED_FACT
        )
    ][:2]

    forecast = next(
        (
            claim
            for claim in extracted_claims
            if (
                claim.claim_type
                == ClaimType.FORECAST
            )
        ),
        None,
    )

    attributed = next(
        (
            claim
            for claim in extracted_claims
            if (
                claim.claim_type
                == ClaimType.ATTRIBUTED_CLAIM
            )
        ),
        None,
    )

    if (
        len(reported) < 2
        or forecast is None
        or attributed is None
    ):
        raise RuntimeError(
            "Live extraction did not produce the "
            "claim mix required for the visual demo."
        )

    claims = tuple(
        reported
        + [
            forecast,
            attributed,
        ]
    )

    print(
        "SELECTED CLAIMS:",
        len(claims),
    )


    # -------------------------------------------------
    # 4. Synthetic anomaly for integration
    #
    # IMPORTANT:
    # This is not a claim that this exact anomaly
    # actually occurred. The real anomaly detector
    # remains upstream and separate.
    # -------------------------------------------------

    anomaly = AnomalyEvent(
        anomaly_id="A-NVDA-LIVE-INTEGRATION",
        ticker="NVDA",
        detected_at=datetime(
            2026,
            2,
            26,
            tzinfo=timezone.utc,
        ),
        anomaly_type=(
            "single_security_attention_event"
        ),
        summary=(
            "Synthetic integration anomaly: NVDA "
            "moved unusually relative to its recent "
            "baseline following a financial-results "
            "announcement."
        ),
        severity=0.8,
        related_entities=(),
        metadata={
            "synthetic_test": "true",
        },
    )


    # -------------------------------------------------
    # 5. Competing hypotheses
    # -------------------------------------------------

    hypothesis_run, hypotheses = (
        generate_hypotheses(
            anomaly,
            claims,
            provider,
        )
    )

    # The separate audit stage is authoritative for
    # assumptions. Do not expose assumptions generated
    # during the creative hypothesis stage as if they
    # had already been validated.

    hypotheses = tuple(
        hypothesis.model_copy(
            update={
                "assumptions": (),
            }
        )
        for hypothesis in hypotheses
    )

    print(
        "HYPOTHESES:",
        len(hypotheses),
    )


    # -------------------------------------------------
    # 6. Audit hidden premises / evidence gaps
    # -------------------------------------------------

    audit_run, audits = (
        audit_hypotheses(
            anomaly,
            claims,
            hypotheses,
            provider,
        )
    )

    print(
        "HYPOTHESIS AUDITS:",
        len(audits),
    )


    # -------------------------------------------------
    # 7. Claim ↔ hypothesis relationships
    #
    # One model call per hypothesis.
    # -------------------------------------------------

    relation_runs, assessments = (
        assess_relationships(
            claims,
            hypotheses,
            provider,
        )
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
    # 8. Assemble semantic investigation state
    # -------------------------------------------------

    state = InvestigationState(
        investigation_id=(
            "INV-NVDA-LIVE-INTEGRATION"
        ),

        anomaly=anomaly,

        documents=(
            document,
        ),

        model_runs=(
            claim_run,
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
    # 9. Build stable frontend graph contract
    # -------------------------------------------------

    graph = build_investigation_graph(
        state
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
    # 10. Persist graph
    # -------------------------------------------------

    payload = (
        graph.model_dump_json(
            indent=2
        )
        + "\n"
    )

    outputs = [
        Path(
            "data/fixtures/"
            "investigation_live_nvidia.json"
        ),

        Path(
            "frontend/public/"
            "investigation_live_nvidia.json"
        ),
    ]

    for output in outputs:
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_text(
            payload
        )

        print(
            "WROTE:",
            output,
        )


if __name__ == "__main__":
    main()
