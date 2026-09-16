from datetime import datetime, timezone

from financial_assistant.domain import (
    AnomalyEvent,
    ArgumentNodeKind,
    Calculation,
    ClaimType,
    EvidenceRequirement,
    ExtractedClaim,
    Hypothesis,
    Inference,
    InvestigationState,
    ModelOperation,
    ModelRun,
    Observation,
    RelationKind,
    RelationshipAssessment,
    SourceDocument,
)


DEMO_TIME = datetime(
    2026,
    9,
    16,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_demo_state() -> InvestigationState:
    """
    Canonical deterministic ClaimGraph demo.

    No LLM or network is involved. This represents
    the target shape that the live pipeline will
    eventually produce.
    """

    nvidia_extract = ModelRun(
        run_id="MR-NVIDIA-EXTRACT",
        provider="nvidia",
        model="demo-nvidia-model",
        operation=ModelOperation.CLAIM_EXTRACTION,
        prompt_version="claim-extraction-v1",
        created_at=DEMO_TIME,
    )

    apertus_extract = ModelRun(
        run_id="MR-APERTUS-EXTRACT",
        provider="apertus",
        model="demo-apertus-model",
        operation=ModelOperation.CLAIM_EXTRACTION,
        prompt_version="claim-extraction-v1",
        created_at=DEMO_TIME,
    )

    hypothesis_run = ModelRun(
        run_id="MR-HYPOTHESIS",
        provider="nvidia",
        model="demo-nvidia-model",
        operation=ModelOperation.HYPOTHESIS_GENERATION,
        prompt_version="hypothesis-v1",
        created_at=DEMO_TIME,
    )

    relation_run = ModelRun(
        run_id="MR-RELATION",
        provider="nvidia",
        model="demo-nvidia-model",
        operation=ModelOperation.RELATION_ASSESSMENT,
        prompt_version="relation-v1",
        created_at=DEMO_TIME,
    )

    fundamental_run = ModelRun(
        run_id="MR-FUNDAMENTAL",
        provider="nvidia",
        model="demo-nvidia-model",
        operation=(
            ModelOperation.FUNDAMENTAL_TEST_SELECTION
        ),
        prompt_version="fundamental-test-v1",
        created_at=DEMO_TIME,
    )

    inference_run = ModelRun(
        run_id="MR-INFERENCE",
        provider="apertus",
        model="demo-apertus-model",
        operation=ModelOperation.INFERENCE,
        prompt_version="inference-v1",
        created_at=DEMO_TIME,
    )

    news = SourceDocument(
        document_id="DOC-NEWS-1",
        title=(
            "Illustrative article about "
            "new export restrictions"
        ),
        publisher="Demo News",
        url="https://example.com/news-1",
        published_at=DEMO_TIME,
        retrieved_at=DEMO_TIME,
        text=(
            "New export rules could restrict "
            "shipments of affected products."
        ),
        lineage_id="LINEAGE-NEWS-1",
    )

    filing = SourceDocument(
        document_id="DOC-FILING-1",
        title="Illustrative company filing",
        publisher="SEC EDGAR",
        url="https://example.com/filing",
        published_at=DEMO_TIME,
        retrieved_at=DEMO_TIME,
        text="Illustrative filing text.",
        lineage_id="LINEAGE-FILING-1",
    )

    nvidia_claim = ExtractedClaim(
        claim_id="C-NVIDIA-1",
        text=(
            "New export rules could restrict "
            "shipments of affected products."
        ),
        claim_type=ClaimType.REPORTED_FACT,
        document_id="DOC-NEWS-1",
        source_quote=(
            "New export rules could restrict "
            "shipments of affected products."
        ),
        model_run_id="MR-NVIDIA-EXTRACT",
    )

    apertus_claim = ExtractedClaim(
        claim_id="C-APERTUS-1",
        text=(
            "New export rules create material "
            "revenue risk."
        ),
        claim_type=ClaimType.INTERPRETATION,
        document_id="DOC-NEWS-1",
        source_quote=(
            "New export rules could restrict "
            "shipments of affected products."
        ),
        model_run_id="MR-APERTUS-EXTRACT",
    )

    regulatory = Hypothesis(
        hypothesis_id="H-REGULATORY",
        text=(
            "The anomaly reflects material "
            "company-specific regulatory risk."
        ),
        model_run_id="MR-HYPOTHESIS",
    )

    sector = Hypothesis(
        hypothesis_id="H-SECTOR",
        text=(
            "The anomaly is mainly broad "
            "sector noise."
        ),
        model_run_id="MR-HYPOTHESIS",
    )

    nvidia_support = RelationshipAssessment(
        assessment_id="RA-NVIDIA",

        source_kind=ArgumentNodeKind.CLAIM,
        source_id="C-NVIDIA-1",

        target_kind=ArgumentNodeKind.HYPOTHESIS,
        target_id="H-REGULATORY",

        relation=RelationKind.SUPPORTS,
        strength=0.65,

        rationale=(
            "The claim establishes a plausible "
            "company-specific regulatory "
            "mechanism, but not materiality."
        ),

        missing_information=(
            "economic materiality",
        ),

        model_run_id="MR-RELATION",
    )

    apertus_support = RelationshipAssessment(
        assessment_id="RA-APERTUS",

        source_kind=ArgumentNodeKind.CLAIM,
        source_id="C-APERTUS-1",

        target_kind=ArgumentNodeKind.HYPOTHESIS,
        target_id="H-REGULATORY",

        relation=RelationKind.SUPPORTS,
        strength=0.85,

        rationale=(
            "The extracted interpretation "
            "explicitly asserts material risk."
        ),

        assumptions=(
            "The article supports the added "
            "materiality judgement.",
        ),

        model_run_id="MR-RELATION",
    )

    requirement = EvidenceRequirement(
        requirement_id="ER-MATERIALITY",
        hypothesis_id="H-REGULATORY",

        question=(
            "How large is the directly affected "
            "revenue exposure?"
        ),

        rationale=(
            "The news claim alone does not "
            "establish economic materiality."
        ),

        model_run_id="MR-FUNDAMENTAL",
    )

    affected = Observation(
        observation_id="O-AFFECTED",
        name="Affected revenue",
        value=12.0,
        unit="demo units",
        source_document_id="DOC-FILING-1",
    )

    total = Observation(
        observation_id="O-TOTAL",
        name="Total revenue",
        value=100.0,
        unit="demo units",
        source_document_id="DOC-FILING-1",
    )

    exposure = Calculation(
        calculation_id="CALC-EXPOSURE",
        label="Direct exposure ratio",
        expression="12 / 100 * 100",
        input_observation_ids=(
            "O-AFFECTED",
            "O-TOTAL",
        ),
        value=12.0,
        unit="%",
    )

    materiality = Inference(
        inference_id="I-MATERIALITY",

        text=(
            "Direct exposure is non-trivial, "
            "but does not alone establish the "
            "full earnings effect."
        ),

        derived_from_ids=(
            "CALC-EXPOSURE",
        ),

        model_run_id="MR-INFERENCE",
    )

    materiality_support = RelationshipAssessment(
        assessment_id="RA-MATERIALITY",

        source_kind=ArgumentNodeKind.INFERENCE,
        source_id="I-MATERIALITY",

        target_kind=ArgumentNodeKind.HYPOTHESIS,
        target_id="H-REGULATORY",

        relation=RelationKind.SUPPORTS,
        strength=0.55,

        rationale=(
            "The filing-derived calculation "
            "provides some support for economic "
            "materiality, while leaving the full "
            "earnings effect unresolved."
        ),

        model_run_id="MR-RELATION",
    )

    return InvestigationState(
        investigation_id="INV-DEMO-001",

        anomaly=AnomalyEvent(
            anomaly_id="A-DEMO-001",
            ticker="EXMPL",
            detected_at=DEMO_TIME,
            anomaly_type="price_volume",
            summary=(
                "Abnormal downside price and "
                "volume event"
            ),
            severity=0.87,
        ),

        documents=(
            news,
            filing,
        ),

        model_runs=(
            nvidia_extract,
            apertus_extract,
            hypothesis_run,
            relation_run,
            fundamental_run,
            inference_run,
        ),

        claims=(
            nvidia_claim,
            apertus_claim,
        ),

        hypotheses=(
            regulatory,
            sector,
        ),

        relationship_assessments=(
            nvidia_support,
            apertus_support,
            materiality_support,
        ),

        evidence_requirements=(
            requirement,
        ),

        observations=(
            affected,
            total,
        ),

        calculations=(
            exposure,
        ),

        inferences=(
            materiality,
        ),
    )
