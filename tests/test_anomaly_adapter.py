from datetime import date

from financial_assistant.anomaly_detection import (
    PairAnomaly,
    pair_anomaly_to_event,
)

from financial_assistant.claimgraph.builder_v2 import (
    build_investigation_graph,
)

from financial_assistant.domain import (
    InvestigationState,
)


def make_pair_anomaly() -> PairAnomaly:
    return PairAnomaly(
        anomaly_id="PAIR-AAA-BBB-2026-09-16",

        ticker_a="AAA",
        ticker_b="BBB",

        metric="close",

        monitoring_start=date(
            2026,
            9,
            1,
        ),

        monitoring_end=date(
            2026,
            9,
            16,
        ),

        first_flag=date(
            2026,
            9,
            14,
        ),

        threshold=2.0,

        n_days_flagged=3,

        z_score=2.7,
        max_abs_z=3.1,

        relative_direction=(
            "a_above_equilibrium"
        ),

        beta=1.12,
        const=0.04,

        formation_start=date(
            2021,
            9,
            1,
        ),

        formation_end=date(
            2026,
            8,
            31,
        ),
    )


def test_pair_anomaly_converts_to_claimgraph_event():
    event = pair_anomaly_to_event(
        make_pair_anomaly()
    )

    assert event.anomaly_id == (
        "PAIR-AAA-BBB-2026-09-16"
    )

    assert event.ticker == "AAA"

    assert event.related_entities == (
        "BBB",
    )

    assert event.anomaly_type == (
        "cointegration_spread_deviation"
    )

    assert event.metadata["pair"] == (
        "AAA/BBB"
    )

    assert event.metadata["z_score"] == 2.7
    assert event.metadata["threshold"] == 2.0


def test_pair_anomaly_metadata_survives_graph_build():
    event = pair_anomaly_to_event(
        make_pair_anomaly()
    )

    state = InvestigationState(
        investigation_id="INV-PAIR-1",
        anomaly=event,
    )

    graph = build_investigation_graph(
        state
    )

    anomaly_node = next(
        node
        for node in graph.nodes
        if node.kind.value == "anomaly"
    )

    assert (
        anomaly_node.data["metadata"]["pair"]
        == "AAA/BBB"
    )

    assert (
        anomaly_node.data[
            "related_entities"
        ]
        == ["BBB"]
    )
