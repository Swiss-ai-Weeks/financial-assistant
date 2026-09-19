from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

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
You generate retrieval concepts for an evidence
investigation.

The supplied entities may be security tickers,
market identifiers or other domain entities.

Use the supplied context, research question and
rationale to interpret the entities when reasonably
confident.

If an identifier is genuinely ambiguous, do not
invent an identity. Preserve the identifier or use
contextual terms that help disambiguate it.

Your output contains SEARCH HYPOTHESES.

Search hypotheses are NOT:
- evidence;
- factual findings;
- causal conclusions;
- explanations already established.

Generate concepts that could help investigate the
research question.

For each query provide:

1. text

   A concise search concept.

2. proximity

   Either:

   "direct"
       The query directly concerns the investigated
       entity or event.

   "indirect"
       The query concerns surrounding context,
       mechanisms, conditions or potentially relevant
       external information.

3. relation

   A short snake_case label describing how this
   concept relates to the research task.

   The relation vocabulary is OPEN-ENDED.

   Possible examples include:

   entity
   sector
   competitor
   input_cost
   consumer_demand
   monetary_policy
   regulatory_environment
   geopolitical_disruption
   management_change
   litigation
   technology
   supply_chain
   labour_relations
   market_sentiment

   These are examples only.

   Do not force a concept into one of these labels.
   Invent a different concise snake_case relation when
   that better describes the search rationale.

4. entities

   Identifiers from the supplied research task that
   are relevant to this query.

5. reason

   A concise explanation of why this search may help
   investigate the task.

Use neutral search concepts that do not presuppose
that an event actually occurred.

For example:

prefer "economic conditions"
over "economic downturn";

prefer "jet fuel prices"
over "jet fuel price spike";

prefer "travel demand"
over "travel demand collapse".

A relation describes retrieval intent only.
It does not establish that the relationship exists
or caused the observed anomaly.

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
