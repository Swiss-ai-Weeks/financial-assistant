from __future__ import annotations

from hashlib import sha1

from financial_assistant.domain import (
    ArgumentNodeKind,
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

    for bundle in state.fundamentals:
        if bundle.status == "unavailable":
            missing_id = _node_id("missing_evidence", f"fundamentals-{bundle.ticker}")
            nodes.append(GraphNode(node_id=missing_id, kind=NodeKind.MISSING_EVIDENCE,
                label=f"{bundle.ticker}: fundamentals unavailable",
                data={"ticker": bundle.ticker, "provider": "SEC EDGAR", "warnings": list(bundle.warnings),
                      "as_of": bundle.as_of.isoformat(), "execution": bundle.provider_execution_metadata}))
            edges.append(GraphEdge(edge_id=_edge_id(anomaly_node_id, EdgeKind.REQUIRES, missing_id),
                                   source=anomaly_node_id, target=missing_id, kind=EdgeKind.REQUIRES))

    for bundle in state.fundamentals:
        if not bundle.snapshots:
            continue
        company_id = _node_id("context", f"fundamentals-{bundle.ticker}")
        nodes.append(GraphNode(node_id=company_id, kind=NodeKind.CONTEXT,
            label=f"{bundle.ticker} fundamentals", data={"subtype": "fundamentals", "entity": bundle.ticker}))
        edges.append(GraphEdge(edge_id=_edge_id(company_id, EdgeKind.CONTEXT_FOR, anomaly_node_id),
            source=company_id, target=anomaly_node_id, kind=EdgeKind.CONTEXT_FOR))
        for index, snapshot in enumerate(bundle.snapshots):
            identifier = _node_id("context", snapshot.snapshot_id)
            nodes.append(GraphNode(node_id=identifier, kind=NodeKind.CONTEXT,
                label=f"{bundle.ticker} {snapshot.fiscal_year}-{snapshot.fiscal_quarter}",
                data={**snapshot.model_dump(mode="json"), "older_quarter": index < len(bundle.snapshots)-4}))
            edges.append(GraphEdge(edge_id=_edge_id(identifier, EdgeKind.CONTEXT_FOR, company_id),
                source=identifier, target=company_id, kind=EdgeKind.CONTEXT_FOR))
            for metric_id in snapshot.metrics.values():
                target = _node_id("observation" if metric_id in observations else "calculation", metric_id)
                edges.append(GraphEdge(edge_id=_edge_id(identifier, EdgeKind.DERIVED_FROM, target),
                    source=identifier, target=target, kind=EdgeKind.DERIVED_FROM,
                    data={"role": "snapshot membership; grouping only, not arithmetic"}))
            for calculation in bundle.calculations:
                if calculation.frequency == 'quarterly' and calculation.period_end == snapshot.period_end and calculation.status == 'available':
                    target = _node_id('calculation', calculation.calculation_id)
                    edges.append(GraphEdge(edge_id=_edge_id(identifier, EdgeKind.CONTEXT_FOR, target),
                        source=identifier, target=target, kind=EdgeKind.CONTEXT_FOR))

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

        document_data["observed_at"] = state.anomaly.metadata.get(
            "observed_at", state.anomaly.detected_at.isoformat()
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

    from financial_assistant.llm.evidence_arguments import relationship_diagnostics
    for run in state.model_runs:
        run_data = run.model_dump(mode="json", exclude_none=True)
        if run.operation.value == 'relation_assessment':
            assessed = tuple(a for a in state.relationship_assessments if a.model_run_id == run.run_id)
            run_data['relationship_diagnostics'] = relationship_diagnostics(assessed)
            # Includes unrelated judgments without inventing epistemic graph edges.
            run_data['assessments'] = [a.model_dump(mode='json') for a in assessed]
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
                data=run_data,
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
    # -------------------------------------------------
    # Hypothesis audits
    # -------------------------------------------------

    for audit in state.hypothesis_audits:
        if audit.hypothesis_id not in hypotheses:
            raise ValueError(
                f"Hypothesis audit {audit.audit_id} "
                "references unknown hypothesis_id "
                f"{audit.hypothesis_id}"
            )

        if audit.model_run_id not in model_runs:
            raise ValueError(
                f"Hypothesis audit {audit.audit_id} "
                "references unknown model_run_id "
                f"{audit.model_run_id}"
            )

        hypothesis_node_id = _node_id(
            "hypothesis",
            audit.hypothesis_id,
        )

        run_node_id = _node_id(
            "modelrun",
            audit.model_run_id,
        )

        # ---------------------------------------------
        # Explicit assumptions
        # ---------------------------------------------

        for index, assumption in enumerate(
            audit.assumptions,
            start=1,
        ):
            assumption_node_id = _node_id(
                "assumption",
                f"{audit.audit_id}:{index}",
            )

            nodes.append(
                GraphNode(
                    node_id=assumption_node_id,
                    kind=NodeKind.ASSUMPTION,
                    label=assumption,
                    data={
                        "audit_id": audit.audit_id,
                        "hypothesis_id":
                            audit.hypothesis_id,
                        "model_run_id":
                            audit.model_run_id,
                    },
                )
            )

            edges.append(
                GraphEdge(
                    edge_id=_edge_id(
                        hypothesis_node_id,
                        EdgeKind.REQUIRES,
                        assumption_node_id,
                    ),
                    source=hypothesis_node_id,
                    target=assumption_node_id,
                    kind=EdgeKind.REQUIRES,
                )
            )

            edges.append(
                GraphEdge(
                    edge_id=_edge_id(
                        assumption_node_id,
                        EdgeKind.PRODUCED_BY,
                        run_node_id,
                    ),
                    source=assumption_node_id,
                    target=run_node_id,
                    kind=EdgeKind.PRODUCED_BY,
                )
            )

        # ---------------------------------------------
        # Raw evidence gaps identified by the audit
        # ---------------------------------------------

        for index, missing in enumerate(
            audit.missing_information,
            start=1,
        ):
            missing_node_id = _node_id(
                "missing_evidence",
                f"{audit.audit_id}:{index}",
            )

            nodes.append(
                GraphNode(
                    node_id=missing_node_id,
                    kind=NodeKind.MISSING_EVIDENCE,
                    label=missing,
                    data={
                        "audit_id": audit.audit_id,
                        "hypothesis_id":
                            audit.hypothesis_id,
                        "model_run_id":
                            audit.model_run_id,
                    },
                )
            )

            edges.append(
                GraphEdge(
                    edge_id=_edge_id(
                        hypothesis_node_id,
                        EdgeKind.REQUIRES,
                        missing_node_id,
                    ),
                    source=hypothesis_node_id,
                    target=missing_node_id,
                    kind=EdgeKind.REQUIRES,
                )
            )

            edges.append(
                GraphEdge(
                    edge_id=_edge_id(
                        missing_node_id,
                        EdgeKind.PRODUCED_BY,
                        run_node_id,
                    ),
                    source=missing_node_id,
                    target=run_node_id,
                    kind=EdgeKind.PRODUCED_BY,
                )
            )


    # -------------------------------------------------
    # Epistemic relationship judgements
    # -------------------------------------------------

    relation_to_edge = {
        "supports": EdgeKind.SUPPORTS,
        "contradicts": EdgeKind.CONTRADICTS,
        "weakens": EdgeKind.WEAKENS,
        "context_for": EdgeKind.CONTEXT_FOR,
    }

    argument_indexes = {
        ArgumentNodeKind.CLAIM: claims,
        ArgumentNodeKind.HYPOTHESIS: hypotheses,
        ArgumentNodeKind.OBSERVATION: observations,
        ArgumentNodeKind.CALCULATION: calculations,
        ArgumentNodeKind.INFERENCE: inferences,
    }

    argument_prefixes = {
        ArgumentNodeKind.CLAIM: "claim",
        ArgumentNodeKind.HYPOTHESIS: "hypothesis",
        ArgumentNodeKind.OBSERVATION: "observation",
        ArgumentNodeKind.CALCULATION: "calculation",
        ArgumentNodeKind.INFERENCE: "inference",
    }

    for assessment in state.relationship_assessments:
        source_index = argument_indexes[
            assessment.source_kind
        ]

        target_index = argument_indexes[
            assessment.target_kind
        ]

        if assessment.source_id not in source_index:
            raise ValueError(
                f"Relationship assessment "
                f"{assessment.assessment_id} "
                f"references unknown "
                f"{assessment.source_kind.value} "
                f"{assessment.source_id}"
            )

        if assessment.target_id not in target_index:
            raise ValueError(
                f"Relationship assessment "
                f"{assessment.assessment_id} "
                f"references unknown "
                f"{assessment.target_kind.value} "
                f"{assessment.target_id}"
            )

        if assessment.model_run_id not in model_runs:
            raise ValueError(
                f"Relationship assessment "
                f"{assessment.assessment_id} "
                "references unknown model_run_id "
                f"{assessment.model_run_id}"
            )

        if assessment.relation.value == "unrelated":
            continue

        edge_kind = relation_to_edge[
            assessment.relation.value
        ]

        source_node_id = _node_id(
            argument_prefixes[
                assessment.source_kind
            ],
            assessment.source_id,
        )

        target_node_id = _node_id(
            argument_prefixes[
                assessment.target_kind
            ],
            assessment.target_id,
        )

        edges.append(
            GraphEdge(
                edge_id=_edge_id(
                    source_node_id,
                    edge_kind,
                    target_node_id,
                    assessment.assessment_id,
                ),
                source=source_node_id,
                target=target_node_id,
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

    # Calculations can depend on deterministic intermediate calculations.
    def check_calculation(identifier, path):
        if identifier in path:
            raise ValueError("Calculation dependency cycle")
        if identifier not in calculations:
            raise ValueError(f"Unknown input calculation: {identifier}")
        for dependency in calculations[identifier].input_calculation_ids:
            check_calculation(dependency, path | {identifier})

    for calculation in state.calculations:
        check_calculation(calculation.calculation_id, set())
        source = _node_id("calculation", calculation.calculation_id)
        for identifier in calculation.input_calculation_ids:
            target = _node_id("calculation", identifier)
            edges.append(GraphEdge(edge_id=_edge_id(source, EdgeKind.CALCULATED_FROM, target),
                                   source=source, target=target, kind=EdgeKind.CALCULATED_FROM))
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
        fundamentals=state.fundamentals,
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
