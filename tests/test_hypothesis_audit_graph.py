from financial_assistant.claimgraph.builder_v2 import (
    build_investigation_graph,
)

from financial_assistant.claimgraph.schema_v2 import (
    EdgeKind,
    NodeKind,
)

from financial_assistant.demo import (
    make_demo_state,
)

from financial_assistant.domain import (
    HypothesisAudit,
    ModelOperation,
)


def test_hypothesis_audit_becomes_graph_nodes():
    state = make_demo_state()

    hypothesis = state.hypotheses[0]

    # Reuse the shape of an existing valid ModelRun so
    # this test stays aligned with the domain contract.
    audit_run = state.model_runs[0].model_copy(
        update={
            "run_id": "MR-AUDIT-TEST",
            "operation":
                ModelOperation.HYPOTHESIS_AUDIT,
        }
    )

    audit = HypothesisAudit(
        audit_id="HA-TEST",
        hypothesis_id=hypothesis.hypothesis_id,
        assumptions=(
            (
                "Market participants changed "
                "their valuation."
            ),
        ),
        missing_information=(
            (
                "What were consensus expectations "
                "before the event?"
            ),
        ),
        model_run_id=audit_run.run_id,
    )

    state = state.model_copy(
        update={
            "model_runs":
                state.model_runs
                + (audit_run,),

            "hypothesis_audits":
                (audit,),
        }
    )

    graph = build_investigation_graph(
        state
    )

    assumption_nodes = [
        node
        for node in graph.nodes
        if (
            node.kind
            == NodeKind.ASSUMPTION
            and
            node.data.get("audit_id")
            == audit.audit_id
        )
    ]

    missing_nodes = [
        node
        for node in graph.nodes
        if (
            node.kind
            == NodeKind.MISSING_EVIDENCE
            and
            node.data.get("audit_id")
            == audit.audit_id
        )
    ]

    assert len(assumption_nodes) == 1
    assert len(missing_nodes) == 1

    hypothesis_node_id = (
        f"hypothesis:{hypothesis.hypothesis_id}"
    )

    assert any(
        edge.source == hypothesis_node_id
        and edge.target == assumption_nodes[0].node_id
        and edge.kind == EdgeKind.REQUIRES
        for edge in graph.edges
    )

    assert any(
        edge.source == hypothesis_node_id
        and edge.target == missing_nodes[0].node_id
        and edge.kind == EdgeKind.REQUIRES
        for edge in graph.edges
    )

    assert any(
        edge.source == assumption_nodes[0].node_id
        and edge.kind == EdgeKind.PRODUCED_BY
        for edge in graph.edges
    )

    assert any(
        edge.source == missing_nodes[0].node_id
        and edge.kind == EdgeKind.PRODUCED_BY
        for edge in graph.edges
    )
