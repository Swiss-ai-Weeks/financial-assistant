import pytest
from pydantic import ValidationError

from financial_assistant.retrieval.query_expansion import (
    ExpandedQuery,
    QueryExpansion,
    QueryRelation,
)


def test_query_expansion_preserves_search_intent():
    expansion = QueryExpansion(
        task_id="RQ-UAL",
        queries=(
            ExpandedQuery(
                text="United Airlines",
                relation=QueryRelation.DIRECT,
                entities=("UAL",),
                reason="Canonical company name",
            ),
            ExpandedQuery(
                text="airlines",
                relation=QueryRelation.SECTOR,
                entities=("UAL",),
                reason=(
                    "Sector developments may affect "
                    "United Airlines"
                ),
            ),
            ExpandedQuery(
                text="jet fuel",
                relation=(
                    QueryRelation.POTENTIAL_DRIVER
                ),
                entities=("UAL",),
                reason=(
                    "Fuel is a material operating "
                    "input for airlines"
                ),
            ),
        ),
    )

    assert expansion.task_id == "RQ-UAL"
    assert len(expansion.queries) == 3

    assert (
        expansion.queries[0].relation
        == QueryRelation.DIRECT
    )

    assert (
        expansion.queries[2].text
        == "jet fuel"
    )


def test_query_expansion_limits_query_count():
    queries = tuple(
        ExpandedQuery(
            text=f"concept {i}",
            relation=QueryRelation.MACRO,
            reason="Possible external context",
        )
        for i in range(7)
    )

    with pytest.raises(ValidationError):
        QueryExpansion(
            task_id="RQ-TOO-MANY",
            queries=queries,
        )


from datetime import datetime, timezone

from financial_assistant.research.models import (
    ResearchSourceClass,
    ResearchTask,
    ResearchTaskKind,
)

from financial_assistant.retrieval.query_expansion import (
    expand_research_task,
)


class FakeLLM:
    def complete_json(
        self,
        *,
        system: str,
        user: str,
        reasoning: bool = False,
    ):
        return {
            "task_id": "RQ-GS",
            "queries": [
                {
                    "text": "Goldman Sachs",
                    "relation": "direct",
                    "entities": ["GS"],
                    "reason": (
                        "Likely company represented "
                        "by GS in this financial context"
                    ),
                },
                {
                    "text": "investment banking",
                    "relation": "sector",
                    "entities": ["GS"],
                    "reason": (
                        "Relevant industry context"
                    ),
                },
                {
                    "text": "interest rates",
                    "relation": (
                        "potential_driver"
                    ),
                    "entities": ["GS"],
                    "reason": (
                        "Potential external driver "
                        "worth investigating"
                    ),
                },
            ],
        }


def test_llm_expands_ticker_from_context():
    task = ResearchTask(
        task_id="RQ-GS",
        kind=ResearchTaskKind.RECENT_NEWS,
        entities=("GS",),
        question=(
            "What recent information could "
            "help explain movement in GS?"
        ),
        rationale=(
            "Investigate a detected market anomaly."
        ),
        source_preferences=(
            ResearchSourceClass.NEWS,
        ),
        lookback_days=30,
        priority=1,
    )

    expansion = expand_research_task(
        FakeLLM(),
        task,
        as_of=datetime(
            2026,
            9,
            17,
            tzinfo=timezone.utc,
        ),
    )

    assert expansion.task_id == "RQ-GS"

    assert (
        expansion.queries[0].text
        == "Goldman Sachs"
    )

    assert (
        expansion.queries[0].entities
        == ("GS",)
    )
