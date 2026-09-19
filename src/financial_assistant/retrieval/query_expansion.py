from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

import re
from typing import Protocol


class QueryProximity(StrEnum):
    """
    Structural distance between a retrieval concept
    and the entity or question being investigated.

    This is deliberately small and stable.

    DIRECT:
        the concept directly identifies or describes
        the investigated entity/event.

    INDIRECT:
        the concept describes surrounding context,
        mechanisms, conditions or other potentially
        relevant information.
    """

    DIRECT = "direct"
    INDIRECT = "indirect"



class ExpandedQuery(BaseModel):
    """
    One explicit retrieval hypothesis.

    `proximity` is controlled because direct versus
    indirect is structurally meaningful.

    `relation` is deliberately open-ended because
    ClaimGraph should not assume in advance every way
    information might relate to a research question.

    Example relation labels:

        entity
        sector
        competitor
        input_cost
        consumer_demand
        monetary_policy
        regulatory_environment
        geopolitical_disruption
        labour_relations
        management_change

    These are examples, not an allowed-values list.

    A relation describes search intent. It does not
    establish that the relationship exists or caused
    the observed anomaly.
    """

    text: str = Field(
        min_length=2,
        max_length=120,
    )

    proximity: QueryProximity

    relation: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    entities: tuple[str, ...] = ()

    reason: str = Field(
        min_length=3,
        max_length=300,
    )

    @field_validator(
            "relation",
            mode="before",
            )

    @classmethod
    def normalize_relation(
            cls,
            value: object,
            ) -> object:
            """
            Normalize an open-ended semantic relation into
            a stable machine-readable label.

            The semantic vocabulary remains open.

            Examples:

                "financial performance"
                -> "financial_performance"

                "M&A / deal activity"
                -> "m_a_deal_activity"

            This is formatting normalization only. It does
            not map relations into a predefined taxonomy.
            """

            if not isinstance(value, str):
                return value

            normalized = re.sub(
                r"[^a-z0-9]+",
                "_",
                value.strip().lower(),
            ).strip("_")

            if not normalized:
                raise ValueError(
                    "relation must contain "
                    "a meaningful label"
                )

            return normalized
        



class QueryExpansion(BaseModel):
    """
    Structured output from the query-expansion step.
    """

    task_id: str

    queries: tuple[
        ExpandedQuery,
        ...
    ] = Field(
        min_length=1,
        max_length=6,
    )

from datetime import datetime
from financial_assistant.llm.provider import (
    StructuredLLM,
)

from financial_assistant.research.models import (
    ResearchTask,
)


QUERY_EXPANSION_PROMPT_VERSION = (
    "query-expansion-v1"
)


SYSTEM_PROMPT = """
Generate concise semantic retrieval concepts, not
verbose search-engine instructions.

When an entity is a ticker or market identifier,
resolve it to the canonical company or security name
when reasonably confident.

For every entity-specific task, include at least one
DIRECT query whose text is the canonical entity name
alone.

Examples:

"GS" -> "Goldman Sachs"
"UAL" -> "United Airlines"

Do not invent a name if the identifier is genuinely
ambiguous.

The retrieval layer already knows the investigation
date and applies date filtering separately.

Therefore DO NOT put temporal instructions into the
query text such as:

"past week"
"last 450 days"
"prior to 2026-03-20"
"as of 2026-03-20"

Likewise avoid generic search-engine filler when a
more specific concept is possible:

avoid:
"GS recent corporate announcements"

prefer:
"Goldman Sachs"

avoid:
"UAL news sentiment analysis"

prefer:
"United Airlines"
or:
"airline market sentiment"

avoid:
"GS SEC filings 450 days prior to 2026-03-20"

prefer:
"Goldman Sachs SEC filings"

Keep each query focused on the information concept
being sought.

Good examples:

"Goldman Sachs"
"Goldman Sachs earnings"
"Goldman Sachs regulation"
"United Airlines"
"United Airlines earnings"
"airline fuel costs"
"travel demand"
"aviation regulation"

The relation label remains open-ended and should
describe WHY the concept is relevant.

Search hypotheses are not evidence and must not
presuppose that the proposed relationship is true.


Return between 2 and 6 queries.

Return only JSON in this form:

{
  "task_id": "...",
  "queries": [
    {
      "text": "...",
      "proximity": "direct",
      "relation": "entity",
      "entities": ["..."],
      "reason": "..."
    }
  ]
}
""".strip()



class QueryExpander(Protocol):
    """
    Contract for anything capable of expanding one
    semantic ResearchTask into explicit retrieval
    hypotheses.

    This class contains no implementation.

    A normal function satisfies this Protocol if it
    accepts:

        task
        as_of=<datetime>

    and returns QueryExpansion.
    """

    def __call__(
        self,
        task: ResearchTask,
        *,
        as_of: datetime,
    ) -> QueryExpansion:
        ...


def build_query_expansion_prompt(
    task: ResearchTask,
    *,
    as_of: datetime,
) -> str:
    """
    Render the semantic research requirement for the
    model.

    Notice that we provide the ResearchTask itself,
    rather than the old web-search query string.
    """

    entities = ", ".join(task.entities)

    source_preferences = ", ".join(
        preference.value
        for preference in task.source_preferences
    )

    return f"""
RESEARCH CUTOFF:
{as_of.isoformat()}

TASK ID:
{task.task_id}

TASK TYPE:
{task.kind.value}

ENTITIES / TICKERS:
{entities}

QUESTION:
{task.question}

RATIONALE:
{task.rationale}

PREFERRED SOURCE CLASSES:
{source_preferences}

LOOKBACK DAYS:
{task.lookback_days}

FORWARD DAYS:
{task.forward_days}

Generate retrieval concepts for this research task.

Remember:

- infer entity names from context only when confident;
- do not make causal claims;
- indirect concepts are things to investigate,
  not explanations already established;
- keep queries concise;
- return no more than 6 queries.
""".strip()


def expand_research_task(
    provider: StructuredLLM,
    task: ResearchTask,
    *,
    as_of: datetime,
) -> QueryExpansion:
    """
    Use the LLM to convert one semantic ResearchTask
    into a bounded set of retrieval hypotheses.
    """

    raw = provider.complete_json(
        system=SYSTEM_PROMPT,
        user=build_query_expansion_prompt(
            task,
            as_of=as_of,
        ),
        reasoning=False,
    )

    expansion = QueryExpansion.model_validate(
        raw
    )

    if expansion.task_id != task.task_id:
        raise ValueError(
            "Query expansion changed task_id: "
            f"expected {task.task_id!r}, "
            f"received {expansion.task_id!r}"
        )

    # Prevent exact duplicate queries from wasting
    # retrieval budget.
    seen: set[str] = set()
    unique: list[ExpandedQuery] = []

    for query in expansion.queries:
        normalized = (
            query.text
            .strip()
            .casefold()
        )

        if normalized in seen:
            continue

        seen.add(normalized)
        unique.append(query)

    if not unique:
        raise ValueError(
            "Query expansion produced no "
            "usable queries."
        )

    return QueryExpansion(
        task_id=expansion.task_id,
        queries=tuple(unique),
    )
