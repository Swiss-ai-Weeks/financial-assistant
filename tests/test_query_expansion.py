import pytest
from pydantic import ValidationError

from financial_assistant.retrieval.query_expansion import (
    ExpandedQuery,
    QueryExpansion,
    QueryProximity,
)


def test_query_expansion_preserves_search_intent():
    expansion = QueryExpansion(
        task_id="RQ-UAL",
        queries=(
            ExpandedQuery(
                    text="United Airlines",
                    proximity=QueryProximity.DIRECT,
                    relation="entity",
                    entities=("UAL",),
                    reason="Direct company-specific retrieval concept.",
            ),
			ExpandedQuery(
					text="airlines",
					proximity=QueryProximity.INDIRECT,
					relation="sector",
					entities=("UAL",),
					reason=(
						"Sector developments may provide "
						"relevant context for United Airlines."
					),
			),
            ExpandedQuery(
				text="jet fuel prices",
				proximity=QueryProximity.INDIRECT,
				relation="input_cost",
				entities=("UAL",),
				reason=(
					"Fuel costs may provide relevant context "
					"for airline economics."
				),
            ),
        ),
    )

    assert expansion.task_id == "RQ-UAL"
    assert len(expansion.queries) == 3

    assert (
        expansion.queries[0].proximity
        == QueryProximity.DIRECT
    )

    assert (
        expansion.queries[0].relation
        == "entity"
    )


def test_query_expansion_limits_query_count():
    queries = tuple(
        ExpandedQuery(
            text=f"concept {i}",
            proximity=QueryProximity.INDIRECT,
			relation="context",
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
					"proximity": "direct",
					"relation": "entity",
					"entities": ["GS"],
					"reason": (
						"Direct company-specific retrieval."
					),
				},
				{
					"text": "investment banking",
					"proximity": "indirect",
					"relation": "sector",
					"entities": ["GS"],
					"reason": (
						"Relevant industry context."
					),
				},
				{
					"text": "interest rates",
					"proximity": "indirect",
					"relation": "monetary_policy",
					"entities": ["GS"],
					"reason": (
						"Monetary conditions may provide "
						"relevant external context."
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


def test_relation_vocabulary_is_open():
    query = ExpandedQuery(
        text="pilot contract negotiations",
        proximity=QueryProximity.INDIRECT,
        relation="labour_relations",
        entities=("UAL",),
        reason=(
            "Labour negotiations may provide relevant "
            "operating and cost context."
        ),
    )

    assert (
        query.relation
        == "labour_relations"
    )


def test_unanticipated_relation_is_allowed():
    query = ExpandedQuery(
        text="aircraft delivery delays",
        proximity=QueryProximity.INDIRECT,
        relation="fleet_capacity_constraint",
        entities=("UAL",),
        reason=(
            "Aircraft availability may affect "
            "capacity planning."
        ),
    )

    assert (
        query.relation
        == "fleet_capacity_constraint"
    )
