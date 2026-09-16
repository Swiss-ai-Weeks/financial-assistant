from __future__ import annotations

from hashlib import sha1

from financial_assistant.domain import (
    InvestigationState,
)

from .schema_v2 import (
    EdgeKind,
    GraphEdge,
    GraphNode,
    InvestigationGraph,
    NodeKind,
)


def _node_id(
    kind: str,
    identifier: str,
) -> str:
    """
    Create stable graph IDs without exposing
    ReactFlow-specific concerns to the domain.
    """

    return f"{kind}:{identifier}"


def _source_id(
    publisher: str,
) -> str:
    """
    A publisher can be referenced by many documents.

    Hashing keeps the graph ID short and deterministic
    while the human-readable publisher remains the
    node label.
    """

    digest = sha1(
        publisher.encode("utf-8")
    ).hexdigest()[:10]

    return f"source:{digest}"


def _edge_id(
    source: str,
    kind: EdgeKind,
    target: str,
    discriminator: str = "",
) -> str:
    """
    Deterministic edge ID.

    discriminator allows two model assessments of the
    same claim/hypothesis pair to remain distinct.
    """

    raw = (
        f"{source}|{kind.value}|"
        f"{target}|{discriminator}"
    )

    digest = sha1(
        raw.encode("utf-8")
    ).hexdigest()[:12]

    return f"edge:{digest}"


def _index(
    items,
    attribute: str,
    object_name: str,
):
    """
    Build an ID lookup and reject duplicate domain IDs.

    Duplicate IDs would make provenance ambiguous,
    so failure here is preferable to silently
    overwriting something.
    """

    result = {}

    for item in items:
        identifier = getattr(
            item,
            attribute,
        )

        if identifier in result:
            raise ValueError(
                f"Duplicate {object_name} "
                f"identifier: {identifier}"
            )

        result[identifier] = item

    return result


def build_investigation_graph(
    state: InvestigationState,
) -> InvestigationGraph:
    """
    Convert typed semantic objects into the stable
    ClaimGraph backend/frontend contract.

    This function contains no LLM logic and performs
    no financial reasoning. Its job is structural:
    preserve meaning and provenance as graph objects.
    """

    documents = _index(
        state.documents,
        "document_id",
        "document",
    )

    model_runs = _index(
        state.model_runs,
        "run_id",
        "model run",
    )

    claims = _index(
        state.claims,
        "claim_id",
        "claim",
    )

    hypotheses = _index(
        state.hypotheses,
        "hypothesis_id",
        "hypothesis",
    )

    requirements = _index(
        state.evidence_requirements,
        "requirement_id",
        "evidence requirement",
    )

    observations = _index(
        state.observations,
        "observation_id",
        "observation",
    )

    calculations = _index(
        state.calculations,
        "calculation_id",
        "calculation",
    )

    inferences = _index(
        state.inferences,
        "inference_id",
        "inference",
    )

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    anomaly_node_id = _node_id(
        "anomaly",
        state.anomaly.anomaly_id,
    )

    nodes.append(
        GraphNode(
            node_id=anomaly_node_id,
            kind=NodeKind.ANOMALY,
            label=state.anomaly.summary,
            data=state.anomaly.model_dump(
                mode="json"
            ),
        )
    )

    # -------------------------------------------------
    # Sources and retrieved documents
    # -------------------------------------------------

    source_nodes: set[str] = set()

    for document in state.documents:
        publisher = (
            document.publisher
            or document.url.host
            or "Unknown source"
        )

        source_node_id = _source_id(
            publisher
        )

        if source_node_id not in source_nodes:
            source_nodes.add(
                source_node_id
            )

            nodes.append(
                GraphNode(
                    node_id=source_node_id,
                    kind=NodeKind.SOURCE,
                    label=publisher,
                    data={
                        "publisher": publisher,
                    },
                )
            )

        document_node_id = _node_id(
            "document",
            document.document_id,
        )

        # The graph/UI receives metadata, not an
        # entire potentially huge article body.
        document_data = (
            document.model_dump(
                mode="json",
                exclude={"text"},
            )
        )

        nodes.append(
            GraphNode(
                node_id=document_node_id,
                kind=NodeKind.DOCUMENT,
                label=document.title,
                data=document_data,
            )
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    document_node_id,
                    EdgeKind.PUBLISHED_BY,
                    source_node_id,
                ),
                source=document_node_id,
                target=source_node_id,
                kind=EdgeKind.PUBLISHED_BY,
            )
        )

    # -------------------------------------------------
    # Execution provenance
    # -------------------------------------------------

    for run in state.model_runs:
        nodes.append(
            GraphNode(
                node_id=_node_id(
                    "modelrun",
                    run.run_id,
                ),
                kind=NodeKind.MODEL_RUN,
                label=(
                    f"{run.provider} / "
                    f"{run.model}: "
                    f"{run.operation.value}"
                ),
                data=run.model_dump(
                    mode="json"
                ),
            )
        )

    # -------------------------------------------------
    # Extracted claims
    # -------------------------------------------------

    for claim in state.claims:
        if claim.document_id not in documents:
            raise ValueError(
                f"Claim {claim.claim_id} "
                "references unknown document_id "
                f"{claim.document_id}"
            )

        if claim.model_run_id not in model_runs:
            raise ValueError(
                f"Claim {claim.claim_id} "
                "references unknown model_run_id "
                f"{claim.model_run_id}"
            )

        claim_node_id = _node_id(
            "claim",
            claim.claim_id,
        )

        document_node_id = _node_id(
            "document",
            claim.document_id,
        )

        run_node_id = _node_id(
            "modelrun",
            claim.model_run_id,
        )

        nodes.append(
            GraphNode(
                node_id=claim_node_id,
                kind=NodeKind.CLAIM,
                label=claim.text,
                data=claim.model_dump(
                    mode="json"
                ),
            )
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    claim_node_id,
                    EdgeKind.EXTRACTED_FROM,
                    document_node_id,
                ),
                source=claim_node_id,
                target=document_node_id,
                kind=EdgeKind.EXTRACTED_FROM,
            )
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    claim_node_id,
                    EdgeKind.PRODUCED_BY,
                    run_node_id,
                ),
                source=claim_node_id,
                target=run_node_id,
                kind=EdgeKind.PRODUCED_BY,
            )
        )

    # -------------------------------------------------
    # Candidate hypotheses
    # -------------------------------------------------

    for hypothesis in state.hypotheses:
        if hypothesis.model_run_id not in model_runs:
            raise ValueError(
                f"Hypothesis "
                f"{hypothesis.hypothesis_id} "
                "references unknown model_run_id "
                f"{hypothesis.model_run_id}"
            )

        hypothesis_node_id = _node_id(
            "hypothesis",
            hypothesis.hypothesis_id,
        )

        run_node_id = _node_id(
            "modelrun",
            hypothesis.model_run_id,
        )

        nodes.append(
            GraphNode(
                node_id=hypothesis_node_id,
                kind=NodeKind.HYPOTHESIS,
                label=hypothesis.text,
                data=hypothesis.model_dump(
                    mode="json"
                ),
            )
        )

        # A hypothesis is explicitly only a
        # candidate explanation of the anomaly.
        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    hypothesis_node_id,
                    EdgeKind.CANDIDATE_EXPLANATION_FOR,
                    anomaly_node_id,
                ),
                source=hypothesis_node_id,
                target=anomaly_node_id,
                kind=(
                    EdgeKind
                    .CANDIDATE_EXPLANATION_FOR
                ),
            )
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    hypothesis_node_id,
                    EdgeKind.PRODUCED_BY,
                    run_node_id,
                ),
                source=hypothesis_node_id,
                target=run_node_id,
                kind=EdgeKind.PRODUCED_BY,
            )
        )

    # -------------------------------------------------
    # Claim ↔ hypothesis relationship judgements
    # -------------------------------------------------

    relation_to_edge = {
        "supports": EdgeKind.SUPPORTS,
        "contradicts": EdgeKind.CONTRADICTS,
        "weakens": EdgeKind.WEAKENS,
        "context_for": EdgeKind.CONTEXT_FOR,
    }

    for assessment in (
        state.relationship_assessments
    ):
        if assessment.claim_id not in claims:
            raise ValueError(
                f"Relationship assessment "
                f"{assessment.assessment_id} "
                "references unknown claim_id "
                f"{assessment.claim_id}"
            )

        if (
            assessment.hypothesis_id
            not in hypotheses
        ):
            raise ValueError(
                f"Relationship assessment "
                f"{assessment.assessment_id} "
                "references unknown hypothesis_id "
                f"{assessment.hypothesis_id}"
            )

        if (
            assessment.model_run_id
            not in model_runs
        ):
            raise ValueError(
                f"Relationship assessment "
                f"{assessment.assessment_id} "
                "references unknown model_run_id "
                f"{assessment.model_run_id}"
            )

        # "unrelated" is analytically useful but
        # does not need a visible graph edge.
        if assessment.relation.value == "unrelated":
            continue

        edge_kind = relation_to_edge[
            assessment.relation.value
        ]

        claim_node_id = _node_id(
            "claim",
            assessment.claim_id,
        )

        hypothesis_node_id = _node_id(
            "hypothesis",
            assessment.hypothesis_id,
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    claim_node_id,
                    edge_kind,
                    hypothesis_node_id,
                    assessment.assessment_id,
                ),
                source=claim_node_id,
                target=hypothesis_node_id,
                kind=edge_kind,
                data={
                    "assessment_id":
                        assessment.assessment_id,

                    "strength":
                        assessment.strength,

                    "rationale":
                        assessment.rationale,

                    "assumptions":
                        list(
                            assessment.assumptions
                        ),

                    "missing_information":
                        list(
                            assessment
                            .missing_information
                        ),

                    # Execution provenance for the
                    # relationship judgement itself.
                    "model_run_id":
                        assessment.model_run_id,
                },
            )
        )

    # -------------------------------------------------
    # Missing / required evidence
    # -------------------------------------------------

    for requirement in state.evidence_requirements:
        if (
            requirement.hypothesis_id
            not in hypotheses
        ):
            raise ValueError(
                f"Evidence requirement "
                f"{requirement.requirement_id} "
                "references unknown hypothesis_id "
                f"{requirement.hypothesis_id}"
            )

        if (
            requirement.model_run_id
            not in model_runs
        ):
            raise ValueError(
                f"Evidence requirement "
                f"{requirement.requirement_id} "
                "references unknown model_run_id "
                f"{requirement.model_run_id}"
            )

        requirement_node_id = _node_id(
            "evidence_requirement",
            requirement.requirement_id,
        )

        hypothesis_node_id = _node_id(
            "hypothesis",
            requirement.hypothesis_id,
        )

        run_node_id = _node_id(
            "modelrun",
            requirement.model_run_id,
        )

        nodes.append(
            GraphNode(
                node_id=requirement_node_id,
                kind=(
                    NodeKind
                    .EVIDENCE_REQUIREMENT
                ),
                label=requirement.question,
                data=requirement.model_dump(
                    mode="json"
                ),
            )
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    hypothesis_node_id,
                    EdgeKind.REQUIRES,
                    requirement_node_id,
                ),
                source=hypothesis_node_id,
                target=requirement_node_id,
                kind=EdgeKind.REQUIRES,
            )
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    requirement_node_id,
                    EdgeKind.PRODUCED_BY,
                    run_node_id,
                ),
                source=requirement_node_id,
                target=run_node_id,
                kind=EdgeKind.PRODUCED_BY,
            )
        )

    # -------------------------------------------------
    # Direct observations
    # -------------------------------------------------

    for observation in state.observations:
        if (
            observation.source_document_id
            not in documents
        ):
            raise ValueError(
                f"Observation "
                f"{observation.observation_id} "
                "references unknown "
                "source_document_id "
                f"{observation.source_document_id}"
            )

        observation_node_id = _node_id(
            "observation",
            observation.observation_id,
        )

        document_node_id = _node_id(
            "document",
            observation.source_document_id,
        )

        nodes.append(
            GraphNode(
                node_id=observation_node_id,
                kind=NodeKind.OBSERVATION,
                label=(
                    f"{observation.name}: "
                    f"{observation.value}"
                    + (
                        f" {observation.unit}"
                        if observation.unit
                        else ""
                    )
                ),
                data=observation.model_dump(
                    mode="json"
                ),
            )
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    observation_node_id,
                    EdgeKind.EXTRACTED_FROM,
                    document_node_id,
                ),
                source=observation_node_id,
                target=document_node_id,
                kind=EdgeKind.EXTRACTED_FROM,
            )
        )

    # -------------------------------------------------
    # Deterministic calculations
    # -------------------------------------------------

    for calculation in state.calculations:
        calculation_node_id = _node_id(
            "calculation",
            calculation.calculation_id,
        )

        nodes.append(
            GraphNode(
                node_id=calculation_node_id,
                kind=NodeKind.CALCULATION,
                label=(
                    f"{calculation.label}: "
                    f"{calculation.value}"
                    + (
                        f" {calculation.unit}"
                        if calculation.unit
                        else ""
                    )
                ),
                data=calculation.model_dump(
                    mode="json"
                ),
            )
        )

        for observation_id in (
            calculation.input_observation_ids
        ):
            if observation_id not in observations:
                raise ValueError(
                    f"Calculation "
                    f"{calculation.calculation_id} "
                    "references unknown "
                    "observation_id "
                    f"{observation_id}"
                )

            observation_node_id = _node_id(
                "observation",
                observation_id,
            )

            edges.append(
                GraphEdge(
                    edge_id=_edge_id(
                        calculation_node_id,
                        EdgeKind.CALCULATED_FROM,
                        observation_node_id,
                    ),
                    source=calculation_node_id,
                    target=observation_node_id,
                    kind=(
                        EdgeKind.CALCULATED_FROM
                    ),
                )
            )

    # -------------------------------------------------
    # Inferences
    # -------------------------------------------------

    # Map raw domain IDs onto typed graph IDs so an
    # inference can derive from a claim, observation,
    # calculation, or another inference.
    derivable_ids: dict[str, str] = {}

    def register_derivable(
        raw_id: str,
        graph_id: str,
    ) -> None:
        if raw_id in derivable_ids:
            raise ValueError(
                "Domain identifiers used in "
                "derived_from_ids must be globally "
                f"unique. Duplicate: {raw_id}"
            )

        derivable_ids[raw_id] = graph_id

    for claim_id in claims:
        register_derivable(
            claim_id,
            _node_id("claim", claim_id),
        )

    for observation_id in observations:
        register_derivable(
            observation_id,
            _node_id(
                "observation",
                observation_id,
            ),
        )

    for calculation_id in calculations:
        register_derivable(
            calculation_id,
            _node_id(
                "calculation",
                calculation_id,
            ),
        )

    for inference_id in inferences:
        register_derivable(
            inference_id,
            _node_id(
                "inference",
                inference_id,
            ),
        )

    for inference in state.inferences:
        if inference.model_run_id not in model_runs:
            raise ValueError(
                f"Inference "
                f"{inference.inference_id} "
                "references unknown model_run_id "
                f"{inference.model_run_id}"
            )

        inference_node_id = _node_id(
            "inference",
            inference.inference_id,
        )

        run_node_id = _node_id(
            "modelrun",
            inference.model_run_id,
        )

        nodes.append(
            GraphNode(
                node_id=inference_node_id,
                kind=NodeKind.INFERENCE,
                label=inference.text,
                data=inference.model_dump(
                    mode="json"
                ),
            )
        )

        for source_id in (
            inference.derived_from_ids
        ):
            if source_id not in derivable_ids:
                raise ValueError(
                    f"Inference "
                    f"{inference.inference_id} "
                    "references unknown "
                    "derived_from_id "
                    f"{source_id}"
                )

            source_node_id = (
                derivable_ids[source_id]
            )

            edges.append(
                GraphEdge(
                    edge_id=_edge_id(
                        inference_node_id,
                        EdgeKind.DERIVED_FROM,
                        source_node_id,
                    ),
                    source=inference_node_id,
                    target=source_node_id,
                    kind=EdgeKind.DERIVED_FROM,
                )
            )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    inference_node_id,
                    EdgeKind.PRODUCED_BY,
                    run_node_id,
                ),
                source=inference_node_id,
                target=run_node_id,
                kind=EdgeKind.PRODUCED_BY,
            )
        )

    return InvestigationGraph(
        investigation_id=(
            state.investigation_id
        ),
        anomaly_id=(
            state.anomaly.anomaly_id
        ),
        ticker=state.anomaly.ticker,
        nodes=tuple(nodes),
        edges=tuple(edges),
    )
