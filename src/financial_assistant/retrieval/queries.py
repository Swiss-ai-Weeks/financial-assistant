from __future__ import annotations

from financial_assistant.research import (
    ResearchTask,
    ResearchTaskKind,
)


def build_search_query(
    task: ResearchTask,
) -> str:
    """
    Deterministically convert a semantic research
    requirement into a simple search query.

    An LLM may improve query formulation later, but
    query generation should not depend on one for the
    MVP.
    """

    entities = " ".join(
        task.entities
    )

    if (
        task.kind
        == ResearchTaskKind.RECENT_NEWS
    ):
        return (
            f"{entities} recent company news"
        )

    if (
        task.kind
        == ResearchTaskKind.UPCOMING_EVENTS
    ):
        return (
            f"{entities} earnings investor relations "
            "upcoming events"
        )

    if (
        task.kind
        == ResearchTaskKind.PRIMARY_DISCLOSURES
    ):
        return (
            f"{entities} SEC filing investor relations"
        )

    if (
        task.kind
        == ResearchTaskKind.SHARED_CONTEXT
    ):
        return (
            f"{entities} sector macro regulatory news"
        )

    raise ValueError(
        f"Unsupported research task kind: "
        f"{task.kind}"
    )
