from __future__ import annotations

from hashlib import sha1

from financial_assistant.domain import (
    AnomalyEvent,
)

from .models import (
    ResearchPlan,
    ResearchSourceClass,
    ResearchTask,
    ResearchTaskKind,
)


def _all_entities(
    anomaly: AnomalyEvent,
) -> tuple[str, ...]:
    """
    Preserve entity order while removing duplicates.

    ticker is currently the primary routing entity.
    related_entities preserves other securities directly
    involved in the anomaly.
    """

    ordered = (
        anomaly.ticker,
        *anomaly.related_entities,
    )

    return tuple(
        dict.fromkeys(ordered)
    )


def _task_id(
    anomaly_id: str,
    kind: ResearchTaskKind,
    entities: tuple[str, ...],
) -> str:
    """
    Deterministic task IDs make repeated planning for the
    same anomaly stable and auditable.
    """

    raw = (
        f"{anomaly_id}|"
        f"{kind.value}|"
        f"{','.join(entities)}"
    )

    digest = sha1(
        raw.encode("utf-8")
    ).hexdigest()[:10]

    return (
        f"RQ-{kind.value.upper()}-"
        f"{digest}"
    )


def _entity_task(
    *,
    anomaly: AnomalyEvent,
    entity: str,
    kind: ResearchTaskKind,
    question: str,
    rationale: str,
    source_preferences: tuple[
        ResearchSourceClass,
        ...
    ],
    lookback_days: int | None = None,
    forward_days: int | None = None,
    priority: int,
) -> ResearchTask:
    entities = (entity,)

    return ResearchTask(
        task_id=_task_id(
            anomaly.anomaly_id,
            kind,
            entities,
        ),
        kind=kind,
        entities=entities,
        question=question,
        rationale=rationale,
        source_preferences=source_preferences,
        lookback_days=lookback_days,
        forward_days=forward_days,
        priority=priority,
    )


def plan_research(
    anomaly: AnomalyEvent,
) -> ResearchPlan:
    """
    Build a neutral information-retrieval plan from an
    anomaly.

    IMPORTANT:
    - no LLM
    - no web search
    - no causal conclusion
    - no investment recommendation

    The output states what information should be sought
    before the anomaly is interpreted.
    """

    entities = _all_entities(
        anomaly
    )

    tasks: list[ResearchTask] = []

    for entity in entities:
        tasks.append(
            _entity_task(
                anomaly=anomaly,
                entity=entity,
                kind=(
                    ResearchTaskKind
                    .RECENT_NEWS
                ),
                question=(
                    f"What recent developments "
                    f"involving {entity} could help "
                    "explain the anomaly without "
                    "assuming causality?"
                ),
                rationale=(
                    "Identify company-specific "
                    "information released near the "
                    "anomaly timestamp."
                ),
                source_preferences=(
                    ResearchSourceClass.NEWS,
                    ResearchSourceClass.COMPANY_IR,
                ),
                lookback_days=7,
                priority=1,
            )
        )

        tasks.append(
            _entity_task(
                anomaly=anomaly,
                entity=entity,
                kind=(
                    ResearchTaskKind
                    .UPCOMING_EVENTS
                ),
                question=(
                    f"What scheduled or announced "
                    f"events for {entity} occur near "
                    "the anomaly and could affect "
                    "its interpretation?"
                ),
                rationale=(
                    "Upcoming earnings, investor "
                    "events, regulatory decisions "
                    "or other scheduled catalysts "
                    "can produce positioning or "
                    "anticipatory market moves."
                ),
                source_preferences=(
                    ResearchSourceClass.CALENDAR,
                    ResearchSourceClass.COMPANY_IR,
                ),
                lookback_days=2,
                forward_days=30,
                priority=2,
            )
        )

        tasks.append(
            _entity_task(
                anomaly=anomaly,
                entity=entity,
                kind=(
                    ResearchTaskKind
                    .PRIMARY_DISCLOSURES
                ),
                question=(
                    f"What recent primary-source "
                    f"disclosures from {entity} are "
                    "relevant to interpreting this "
                    "anomaly?"
                ),
                rationale=(
                    "Primary filings and company "
                    "disclosures can validate or "
                    "contradict explanations found "
                    "in secondary reporting."
                ),
                source_preferences=(
                    ResearchSourceClass.SEC_EDGAR,
                    ResearchSourceClass.COMPANY_IR,
                ),
                lookback_days=450,
                priority=2,
            )
        )

    if len(entities) > 1:
        entity_label = " and ".join(
            entities
        )

        shared_question = (
            "What shared sector, macroeconomic, "
            "regulatory, or market-structure "
            f"developments affecting {entity_label} "
            "could explain the relative divergence?"
        )

        shared_rationale = (
            "A pair anomaly may result from a "
            "company-specific development in either "
            "leg, but it may also reflect a common "
            "sector, macro, regulatory, or technical "
            "factor."
        )

    else:
        entity_label = entities[0]

        shared_question = (
            "What sector, macroeconomic, regulatory, "
            "or market-structure developments "
            f"affecting {entity_label} could explain "
            "the anomaly?"
        )

        shared_rationale = (
            "The anomaly may not be company-specific. "
            "Broader market context must be checked "
            "before attributing it to company news."
        )

    tasks.append(
        ResearchTask(
            task_id=_task_id(
                anomaly.anomaly_id,
                ResearchTaskKind.SHARED_CONTEXT,
                entities,
            ),
            kind=(
                ResearchTaskKind
                .SHARED_CONTEXT
            ),
            entities=entities,
            question=shared_question,
            rationale=shared_rationale,
            source_preferences=(
                ResearchSourceClass.NEWS,
                ResearchSourceClass.MARKET_CONTEXT,
            ),
            lookback_days=7,
            priority=1,
        )
    )

    return ResearchPlan(
        plan_id=(
            f"RP-{anomaly.anomaly_id}"
        ),
        anomaly_id=(
            anomaly.anomaly_id
        ),

        # Using the anomaly timestamp rather than
        # datetime.now() preserves point-in-time
        # behaviour for historical investigations.
        as_of=anomaly.detected_at,

        tasks=tuple(tasks),
    )
