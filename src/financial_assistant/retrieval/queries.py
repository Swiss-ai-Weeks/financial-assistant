from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
)

from financial_assistant.research import (
    ResearchTask,
    ResearchTaskKind,
)


def _temporal_context(
    task: ResearchTask,
    as_of: datetime | None,
) -> str:
    """
    Add deterministic historical context to discovery
    queries.

    This improves search relevance for historical
    investigations.

    IMPORTANT:
    Search terms are NOT the temporal guardrail.
    execute_research_plan() still enforces the actual
    publication-time cutoff.
    """

    if as_of is None:
        return ""

    if (
        task.kind
        == ResearchTaskKind.PRIMARY_DISCLOSURES
    ):
        start = (
            as_of
            - timedelta(
                days=(
                    task.lookback_days
                    or 365
                )
            )
        )

        years = range(
            start.year,
            as_of.year + 1,
        )

        return " ".join(
            str(year)
            for year in years
        )

    if (
        task.kind
        == ResearchTaskKind.UPCOMING_EVENTS
    ):
        end = (
            as_of
            + timedelta(
                days=(
                    task.forward_days
                    or 30
                )
            )
        )

        month_labels = [
            as_of.strftime(
                "%B %Y"
            )
        ]

        end_label = end.strftime(
            "%B %Y"
        )

        if end_label not in month_labels:
            month_labels.append(
                end_label
            )

        return " ".join(
            month_labels
        )

    return as_of.strftime(
        "%B %Y"
    )


def build_search_query(
    task: ResearchTask,
    *,
    as_of: datetime | None = None,
) -> str:
    """
    Deterministically convert a semantic research
    requirement into a simple search query.

    `as_of` optionally orients discovery toward the
    historical investigation period.

    Publication-date validation remains the real
    point-in-time guardrail.
    """

    entities = " ".join(
        task.entities
    )

    if (
        task.kind
        == ResearchTaskKind.RECENT_NEWS
    ):
        base = (
            f"{entities} recent company news"
        )

    elif (
        task.kind
        == ResearchTaskKind.UPCOMING_EVENTS
    ):
        base = (
            f"{entities} earnings investor relations "
            "upcoming events"
        )

    elif (
        task.kind
        == ResearchTaskKind.PRIMARY_DISCLOSURES
    ):
        base = (
            f"{entities} SEC filing investor relations"
        )

    elif (
        task.kind
        == ResearchTaskKind.SHARED_CONTEXT
    ):
        base = (
            f"{entities} sector macro regulatory news"
        )

    else:
        raise ValueError(
            f"Unsupported research task kind: "
            f"{task.kind}"
        )

    temporal = _temporal_context(
        task,
        as_of,
    )

    if not temporal:
        return base

    return (
        f"{base} {temporal}"
    )
