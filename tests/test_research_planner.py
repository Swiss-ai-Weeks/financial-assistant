from datetime import (
    date,
    datetime,
    timezone,
)

from financial_assistant.anomaly_detection import (
    PairAnomaly,
    pair_anomaly_to_event,
)

from financial_assistant.research import (
    ResearchTaskKind,
    plan_research,
)


OBSERVED_AT = datetime(
    2026,
    9,
    16,
    20,
    0,
    tzinfo=timezone.utc,
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


def test_pair_anomaly_generates_research_for_both_legs():
    anomaly = pair_anomaly_to_event(
        make_pair_anomaly(),
        observed_at=OBSERVED_AT,
    )

    plan = plan_research(
        anomaly
    )

    assert plan.anomaly_id == (
        anomaly.anomaly_id
    )

    assert plan.as_of == (
        anomaly.detected_at
    )

    assert plan.as_of == OBSERVED_AT

    entity_tasks = {
        (
            task.kind,
            task.entities,
        )
        for task in plan.tasks
    }

    assert (
        ResearchTaskKind.RECENT_NEWS,
        ("AAA",),
    ) in entity_tasks

    assert (
        ResearchTaskKind.RECENT_NEWS,
        ("BBB",),
    ) in entity_tasks

    assert (
        ResearchTaskKind.UPCOMING_EVENTS,
        ("AAA",),
    ) in entity_tasks

    assert (
        ResearchTaskKind.UPCOMING_EVENTS,
        ("BBB",),
    ) in entity_tasks

    assert (
        ResearchTaskKind.PRIMARY_DISCLOSURES,
        ("AAA",),
    ) in entity_tasks

    assert (
        ResearchTaskKind.PRIMARY_DISCLOSURES,
        ("BBB",),
    ) in entity_tasks

    assert (
        ResearchTaskKind.SHARED_CONTEXT,
        ("AAA", "BBB"),
    ) in entity_tasks

    # 3 per entity + 1 shared-context task.
    assert len(plan.tasks) == 7


def test_research_plan_does_not_assert_causality():
    anomaly = pair_anomaly_to_event(
        make_pair_anomaly(),
        observed_at=OBSERVED_AT,
    )

    plan = plan_research(
        anomaly
    )

    questions = " ".join(
        task.question.lower()
        for task in plan.tasks
    )

    assert "caused by" not in questions
    assert "is caused" not in questions

    # The research layer asks what *could* explain
    # the anomaly rather than deciding the answer.
    assert "could" in questions


def test_research_planning_is_deterministic():
    anomaly = pair_anomaly_to_event(
        make_pair_anomaly(),
        observed_at=OBSERVED_AT,
    )

    first = plan_research(
        anomaly
    )

    second = plan_research(
        anomaly
    )

    assert first == second

    assert (
        tuple(
            task.task_id
            for task in first.tasks
        )
        ==
        tuple(
            task.task_id
            for task in second.tasks
        )
    )
