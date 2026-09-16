import json
from pathlib import Path

from financial_assistant.claimgraph.schema_v2 import (
    InvestigationGraph,
)


def test_demo_fixture_matches_v02_contract() -> None:
    fixture = Path(
        "data/fixtures/investigation_demo.json"
    )

    payload = json.loads(
        fixture.read_text()
    )

    graph = InvestigationGraph.model_validate(
        payload
    )

    assert graph.schema_version == "0.2"
    assert graph.ticker == "EXMPL"

    node_ids = {
        node.node_id
        for node in graph.nodes
    }

    assert "anomaly:A-DEMO-001" in node_ids
    assert "hypothesis:regulatory" in node_ids
    assert "calculation:exposure" in node_ids

    # Every edge must point to real nodes.
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
        if node.kind == "model_run"
    ]

    providers = {
        node.data["provider"]
        for node in model_runs
    }

    assert providers == {
        "nvidia",
        "apertus",
    }
