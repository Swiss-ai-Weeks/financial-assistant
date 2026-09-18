from datetime import (
    datetime,
    timezone,
)

import pytest

from financial_assistant.claimgraph.builder_v2 import (
    build_investigation_graph,
)

from financial_assistant.domain import (
    AnomalyEvent,
    Calculation,
    ClaimType,
    EvidenceRequirement,
    ExtractedClaim,
    Hypothesis,
    Inference,
    ArgumentNodeKind,
    InvestigationState,
    ModelOperation,
    ModelRun,
    Observation,
    RelationKind,
    RelationshipAssessment,
    SourceDocument,
)


NOW = datetime(
    2026,
    9,
    16,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_state() -> InvestigationState:
    extraction_run = ModelRun(
        run_id="MR-EXTRACT",
        provider="nvidia",
        model="demo-model",
        operation=(
            ModelOperation.CLAIM_EXTRACTION
        ),
        prompt_version="v1",
        created_at=NOW,
    )

    hypothesis_run = ModelRun(
        run_id="MR-HYP",
        provider="nvidia",
        model="demo-model",
        operation=(
            ModelOperation
            .HYPOTHESIS_GENERATION
        ),
        prompt_version="v1",
        created_at=NOW,
    )

    relation_run = ModelRun(
        run_id="MR-REL",
        provider="apertus",
        model="demo-model",
        operation=(
            ModelOperation.RELATION_ASSESSMENT
        ),
        prompt_version="v1",
        created_at=NOW,
    )

    evidence_run = ModelRun(
        run_id="MR-EVIDENCE",
        provider="nvidia",
        model="demo-model",
        operation=(
            ModelOperation
            .FUNDAMENTAL_TEST_SELECTION
        ),
        prompt_version="v1",
        created_at=NOW,
    )

    inference_run = ModelRun(
        run_id="MR-INFER",
        provider="apertus",
        model="demo-model",
        operation=ModelOperation.INFERENCE,
        prompt_version="v1",
        created_at=NOW,
    )

    news = SourceDocument(
        document_id="DOC-NEWS",
        title="Export restrictions",
        publisher="Demo News",
        url="https://example.com/news",
        published_at=NOW,
        retrieved_at=NOW,
        text=(
            "New restrictions could affect "
            "shipments of certain products."
        ),
    )

    filing = SourceDocument(
        document_id="DOC-FILING",
        title="Annual filing",
        publisher="SEC EDGAR",
        url="https://example.com/filing",
        published_at=NOW,
        retrieved_at=NOW,
        text="Illustrative filing text.",
    )

    claim = ExtractedClaim(
        claim_id="C1",
        text=(
            "Restrictions could affect "
            "some product shipments."
        ),
        claim_type=ClaimType.REPORTED_FACT,
        document_id="DOC-NEWS",
        source_quote=(
            "restrictions could affect "
            "shipments"
        ),
        model_run_id="MR-EXTRACT",
    )

    hypothesis = Hypothesis(
        hypothesis_id="H1",
        text=(
            "The anomaly may reflect "
            "material regulatory risk."
        ),
        model_run_id="MR-HYP",
    )

    relationship = RelationshipAssessment(
        assessment_id="RA1",
        source_kind=ArgumentNodeKind.CLAIM,
        source_id="C1",
        target_kind=ArgumentNodeKind.HYPOTHESIS,
        target_id="H1",

        relation=RelationKind.SUPPORTS,
        strength=0.65,
        rationale=(
            "The claim establishes a "
            "company-specific regulatory "
            "mechanism."
        ),
        missing_information=(
            "economic materiality",
        ),
        model_run_id="MR-REL",
    )

    requirement = EvidenceRequirement(
        requirement_id="ER1",
        hypothesis_id="H1",
        question=(
            "How large is the directly "
            "affected revenue exposure?"
        ),
        rationale=(
            "Materiality cannot be inferred "
            "from the headline alone."
        ),
        model_run_id="MR-EVIDENCE",
    )

    affected_revenue = Observation(
        observation_id="O1",
        name="Affected revenue",
        value=12.0,
        unit="demo units",
        source_document_id="DOC-FILING",
    )

    total_revenue = Observation(
        observation_id="O2",
        name="Total revenue",
        value=100.0,
        unit="demo units",
        source_document_id="DOC-FILING",
    )

    exposure = Calculation(
        calculation_id="CALC1",
        label="Direct exposure ratio",
        expression="12 / 100 * 100",
        input_observation_ids=(
            "O1",
            "O2",
        ),
        value=12.0,
        unit="%",
    )

    inference = Inference(
        inference_id="I1",
        text=(
            "Direct exposure is non-trivial "
            "but does not establish the full "
            "earnings effect."
        ),
        derived_from_ids=("CALC1",),
        model_run_id="MR-INFER",
    )

    inference_relationship = RelationshipAssessment(
        assessment_id="RA2",

        source_kind=ArgumentNodeKind.INFERENCE,
        source_id="I1",

        target_kind=ArgumentNodeKind.HYPOTHESIS,
        target_id="H1",

        relation=RelationKind.SUPPORTS,
        strength=0.55,

        rationale=(
            "The calculated exposure provides "
            "fundamental support for potential "
            "economic materiality."
        ),

        model_run_id="MR-REL",
    )





    return InvestigationState(
        investigation_id="INV-1",

        anomaly=AnomalyEvent(
            anomaly_id="A1",
            ticker="EXMPL",
            detected_at=NOW,
            anomaly_type="price_volume",
            summary=(
                "Abnormal downside price "
                "and volume event"
            ),
            severity=0.87,
        ),

        documents=(
            news,
            filing,
        ),

        model_runs=(
            extraction_run,
            hypothesis_run,
            relation_run,
            evidence_run,
            inference_run,
        ),

        claims=(claim,),
        hypotheses=(hypothesis,),

        relationship_assessments=(
            relationship,
            inference_relationship,
        ),

        evidence_requirements=(
            requirement,
        ),

        observations=(
            affected_revenue,
            total_revenue,
        ),

        calculations=(exposure,),
        inferences=(inference,),
    )


def test_builder_preserves_epistemic_and_execution_provenance():
    graph = build_investigation_graph(
        make_state()
    )

    node_ids = {
        node.node_id
        for node in graph.nodes
    }

    assert "anomaly:A1" in node_ids
    assert "claim:C1" in node_ids
    assert "hypothesis:H1" in node_ids
    assert "calculation:CALC1" in node_ids
    assert "modelrun:MR-EXTRACT" in node_ids

    relations = {
        (
            edge.source,
            edge.kind.value,
            edge.target,
        )
        for edge in graph.edges
    }

    # Epistemic provenance.
    assert (
        "claim:C1",
        "extracted_from",
        "document:DOC-NEWS",
    ) in relations

    assert (
        "claim:C1",
        "supports",
        "hypothesis:H1",
    ) in relations

    assert (
        "calculation:CALC1",
        "calculated_from",
        "observation:O1",
    ) in relations

    assert (
        "inference:I1",
        "derived_from",
        "calculation:CALC1",
    ) in relations

    # Execution provenance.
    assert (
        "claim:C1",
        "produced_by",
        "modelrun:MR-EXTRACT",
    ) in relations

    assert (
        "inference:I1",
        "supports",
        "hypothesis:H1",
    ) in relations

    # The hypothesis remains explicitly a
    # candidate explanation.
    assert (
        "hypothesis:H1",
        "candidate_explanation_for",
        "anomaly:A1",
    ) in relations

    # No dangling graph edges.
    for edge in graph.edges:
        assert edge.source in node_ids
        assert edge.target in node_ids


def test_builder_rejects_broken_provenance():
    state = make_state()

    bad_claim = state.claims[0].model_copy(
        update={
            "document_id":
                "DOCUMENT-DOES-NOT-EXIST"
        }
    )

    broken = state.model_copy(
        update={
            "claims": (bad_claim,)
        }
    )

    with pytest.raises(
        ValueError,
        match="unknown document_id",
    ):
        build_investigation_graph(
            broken
        )
