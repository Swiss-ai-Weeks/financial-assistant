from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from typing import Protocol

class QueryRelation(StrEnum):
    """
    Why this search concept is relevant to the
    research task.

    These labels describe search intent only.
    They do NOT assert causality or evidential support.
    """

    DIRECT = "direct"
    SECTOR = "sector"
    MACRO = "macro"
    POTENTIAL_DRIVER = "potential_driver"


class ExpandedQuery(BaseModel):
    """
    One search hypothesis generated before retrieval.
    """

    text: str = Field(
        min_length=2,
        max_length=120,
    )

    relation: QueryRelation

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
You generate retrieval queries for a financial
evidence investigation.

The supplied entities are normally publicly traded
security ticker symbols.

Infer the corresponding company or security from
the financial context when reasonably confident.

Do not require or assume a predefined ticker-to-name
mapping.

If a ticker is ambiguous, do not invent an identity.
Keep the ticker or use a query that disambiguates it
using the supplied context.

Your output consists of SEARCH HYPOTHESES, not
claims about what caused the market movement.

Generate queries that may help discover:

1. direct company-specific information;
2. sector or industry developments;
3. macroeconomic or regulatory context;
4. plausible external drivers worth investigating.

Do not state that any proposed driver caused the
anomaly.

Prefer short concepts useful for both newspaper
full-text retrieval and web search.

Examples of appropriate concepts:

"Goldman Sachs"
"United Airlines"
"airlines"
"investment banking"
"jet fuel"
"travel demand"
"interest rates"

Avoid verbose search-engine syntax unless necessary.

Return at most 6 queries.

Return JSON with exactly this structure:

{
  "task_id": "...",
  "queries": [
    {
      "text": "...",
      "relation": "direct|sector|macro|potential_driver",
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
