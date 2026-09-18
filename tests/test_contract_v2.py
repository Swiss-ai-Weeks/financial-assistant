from pathlib import Path

from financial_assistant.claimgraph.schema_v2 import (
    InvestigationGraph,
    NodeKind,
)


def test_demo_fixture_matches_v02_contract() -> None:
    fixture = Path(
        "data/fixtures/investigation_demo.json"
    )

    graph = InvestigationGraph.model_validate_json(
        fixture.read_text()
    )

    assert graph.schema_version == "0.2"
    assert graph.ticker == "EXMPL"
    assert graph.anomaly_id == "A-DEMO-001"

    node_ids = {
        node.node_id
        for node in graph.nodes
    }

    node_kinds = {
        node.kind
        for node in graph.nodes
    }

    # The anomaly identity is part of the
    # investigation contract.
    assert "anomaly:A-DEMO-001" in node_ids

    # The contract test cares about semantic
    # categories, not arbitrary demo object IDs.
    assert NodeKind.ANOMALY in node_kinds
    assert NodeKind.SOURCE in node_kinds
    assert NodeKind.DOCUMENT in node_kinds
    assert NodeKind.CLAIM in node_kinds
    assert NodeKind.HYPOTHESIS in node_kinds
    assert NodeKind.OBSERVATION in node_kinds
    assert NodeKind.CALCULATION in node_kinds
    assert NodeKind.INFERENCE in node_kinds
    assert NodeKind.MODEL_RUN in node_kinds

    # Every relationship must point to nodes
    # that actually exist in the graph.
    for edge in graph.edges:
        assert edge.source in node_ids
        assert edge.target in node_ids


def test_fixture_keeps_model_provenance_visible() -> None:
    fixture = Path(
        "data/fixtures/investigation_demo.json"
    )

    graph = InvestigationGraph.model_validate_json(
        fixture.read_text()
    )

    model_runs = [
        node
        for node in graph.nodes
        if node.kind == NodeKind.MODEL_RUN
    ]

    providers = {
        node.data["provider"]
        for node in model_runs
    }

    assert providers == {
        "nvidia",
        "apertus",
    }


def test_fixture_contains_epistemic_relationships() -> None:
    fixture = Path(
        "data/fixtures/investigation_demo.json"
    )

    graph = InvestigationGraph.model_validate_json(
        fixture.read_text()
    )

    relation_kinds = {
        edge.kind.value
        for edge in graph.edges
    }

    assert "extracted_from" in relation_kinds
    assert "supports" in relation_kinds
    assert "calculated_from" in relation_kinds
    assert "derived_from" in relation_kinds
    assert "produced_by" in relation_kinds
