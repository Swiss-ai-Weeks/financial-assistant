"""
One model call per article: what happened, to whom, of what
kind. Title and summary only, no page fetch, so it is cheap
enough to run on every article the wire brings.

The model proposes; this module verifies and reduces. An
answer that is not the schema is a recorded failure, never
repaired; a security the article concerns is known from the
wire, not from the model.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import ValidationError

from financial_assistant.api.models import NewsItem
from financial_assistant.llm.provider import StructuredLLM, complete_structured

from .models import Direction, Edge, EventType, Extraction, Materiality, Node, NodeKind
from .resolution import Resolver

PROMPT_VERSION = "news-graph-extraction-v2"

MAX_SUMMARY_CHARS = 700

SYSTEM_PROMPT = """
Read ONE news item about a listed company and describe it as
data for a graph. Use only the title and summary given. Do not
use outside knowledge of what happened later.

Return JSON only, with exactly these fields:

{
  "about_company": true if the item is about the company named
      (its business, results, deals, products, people, or a
      development that concerns it directly), false if the
      company is merely mentioned in passing, listed among
      others, or not the subject at all (a wire feed often tags
      a story to the wrong ticker).
  "event_type": one of
      "earnings"            reported results, beats, misses
      "guidance"            outlook raised, cut, withdrawn
      "m_and_a"             acquisition, merger, divestiture, stake
      "regulation"          government or regulator action, export rules, antitrust
      "litigation"          lawsuit, settlement, investigation
      "supply_chain"        supplier, capacity, shortage, tariff on inputs
      "customer"            contract won or lost, partnership, large order
      "product"             launch, recall, technology milestone
      "management"          executive change, board, governance
      "capital"             buyback, dividend, debt or equity issue, rating
      "analyst"             analyst rating, price target, broker note
      "macro"               rates, inflation, sector-wide policy, index flows
      "market_commentary"   price recap, stock-picking list, opinion, "what to watch"
      "other"               none of the above,
  "event": a short canonical label of the concrete thing that
      happened, at most 8 words, naming the parties, for
      example "Oracle OpenAI cloud contract" or "Micron Q3
      results". null for market_commentary and for items with
      no concrete event.
  "entities": up to 6 organisations, people, regulators,
      products or places the item is about, each as
      {"name": "...", "kind": "company|person|regulator|product|place|other"}.
      Use the full proper name ("Applied Materials", not
      "AMAT"). Do NOT include the company the item is about
      unless another party is named too.
  "direction": "positive", "negative" or "neutral": what the
      item implies for the company it is about.
  "materiality": "low", "medium" or "high": how much this
      could change what the company is worth. Recaps, lists
      and opinion are "low".
}
""".strip()


@dataclass(frozen=True)
class Reading:
    """One article, read: its extraction and the graph it adds."""

    article_id: str
    ticker: str
    extraction: Extraction | None
    error: str | None
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


def extract(item: NewsItem, provider: StructuredLLM) -> Extraction:
    summary = " ".join(item.summary.split())[:MAX_SUMMARY_CHARS]

    user = (
        f"Company: {item.ticker}\n"
        f"Published: {item.published_at:%Y-%m-%d}\n"
        f"Source: {item.publisher or 'unknown'}\n"
        f"Title: {item.title}\n"
        + (f"Summary: {summary}\n" if summary else "")
    )

    answer = complete_structured(
        provider,
        system=SYSTEM_PROMPT,
        user=user,
        response_model=Extraction,
    )

    return Extraction.model_validate(answer)


def to_graph(item: NewsItem, extraction: Extraction, resolver: Resolver) -> tuple[list[Node], list[Edge]]:
    """
    The nodes and edges one reading contributes.

    Interaction edges go from the security to what the article
    connects it with: named entities (another security of the
    book when the name is one), the canonical event, and the
    event's type. Each carries the reading's features, which
    are what the temporal graph network learns from.
    """

    security = resolver.security_id(item.ticker)

    if not extraction.about_company:
        # Read and remembered, so it is not read again, but it
        # says nothing about this security.
        return [], []

    features = {
        "event_type": extraction.event_type.value,
        "direction": extraction.direction.value,
        "materiality": extraction.materiality.value,
        "provider": item.provider,
    }

    nodes = [
        Node(security, NodeKind.SECURITY, item.ticker.upper()),
        Node(
            f"article:{item.news_id}",
            NodeKind.ARTICLE,
            item.title,
            {"url": item.url, "publisher": item.publisher, "published_at": item.published_at.isoformat()},
        ),
        Node(resolver.event_type_id(extraction.event_type), NodeKind.EVENT_TYPE, extraction.event_type.value),
    ]
    edges = [
        Edge(security, resolver.event_type_id(extraction.event_type), "reports_type", item.published_at, item.news_id, features),
    ]

    if extraction.event:
        event_id = resolver.event_id(extraction.event_type, extraction.event, item.published_at)

        if event_id:
            nodes.append(Node(event_id, NodeKind.EVENT, extraction.event, {"event_type": extraction.event_type.value}))
            edges.append(Edge(security, event_id, "reports", item.published_at, item.news_id, features))

    for entity in extraction.entities:
        other = resolver.security(entity.name)

        if other and other != item.ticker.upper():
            target = resolver.security_id(other)
            nodes.append(Node(target, NodeKind.SECURITY, other))
        elif other:
            continue
        else:
            target = resolver.entity_id(entity.name, entity.kind)

            if target is None:
                continue

            nodes.append(Node(target, NodeKind.ENTITY, entity.name, {"kind": entity.kind.value}))

        edges.append(Edge(security, target, "mentions", item.published_at, item.news_id, features))

    return nodes, edges


def read_article(item: NewsItem, provider: StructuredLLM, resolver: Resolver) -> Reading:
    try:
        extraction = extract(item, provider)
    except (ValidationError, ValueError, KeyError, TypeError) as error:
        return Reading(item.news_id, item.ticker, None, f"{type(error).__name__}: {error}"[:300], (), ())
    except Exception as error:  # a provider failure: recorded, not raised
        return Reading(item.news_id, item.ticker, None, f"{type(error).__name__}: {error}"[:300], (), ())

    nodes, edges = to_graph(item, extraction, resolver)

    return Reading(item.news_id, item.ticker, extraction, None, tuple(nodes), tuple(edges))


def read_articles(
    items: list[NewsItem],
    provider: StructuredLLM,
    resolver: Resolver,
    *,
    workers: int = 8,
):
    """Readings in the order of `items`, `workers` at a time."""

    if workers <= 1 or len(items) <= 1:
        for item in items:
            yield read_article(item, provider, resolver)
        return

    with ThreadPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(lambda item: read_article(item, provider, resolver), items)


# Kept importable for tests and for the feature vocabulary.
FEATURE_VOCABULARY = {
    "event_type": tuple(e.value for e in EventType),
    "direction": tuple(d.value for d in Direction),
    "materiality": tuple(m.value for m in Materiality),
}
