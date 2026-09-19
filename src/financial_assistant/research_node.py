from __future__ import annotations

import os
import re

from collections import Counter
from datetime import (
    date,
    datetime,
    time,
    timezone,
)
from hashlib import sha1
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
)

from financial_assistant.llm.openai_compatible import (
    OpenAICompatibleProvider,
)
from financial_assistant.llm.registry import (
    get_target,
)

from financial_assistant.research.models import (
    ResearchPlan,
    ResearchSourceClass,
    ResearchTask,
    ResearchTaskKind,
)

from financial_assistant.retrieval.bookreader import (
    CorpusDocumentFetcher,
    CorpusSearchProvider,
)
from financial_assistant.retrieval.fetchers import (
    TrafilaturaDocumentFetcher,
)
from financial_assistant.retrieval.searxng import (
    SearxngSearchProvider,
)
from financial_assistant.retrieval.service import (
    execute_research_plan,
)


class DocumentAssessment(BaseModel):
    """
    Semantic judgement about one retrieved document.

    A retrieved document is NOT automatically evidence.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    relation: Literal[
        "supports",
        "contradicts",
        "context",
        "irrelevant",
        "insufficient",
    ]

    proposition: str | None = None
    source_quote: str | None = None

    rationale: str


ASSESSMENT_SYSTEM_PROMPT = """
You are the evidence-assessment component of ClaimGraph.

You receive:

- one analytical hypothesis or evidence requirement;
- one retrieved source document.

Your task is to determine how, if at all, the document bears on the
selected node.

Important distinctions:

RETRIEVED DOCUMENT
Material that was successfully fetched. Retrieval alone does not make it
evidence.

SUPPORTS
The document contains material that directly supports or materially
satisfies the selected analytical requirement.

CONTRADICTS
The document contains material that directly weakens or contradicts the
selected proposition.

CONTEXT
The document is relevant background but does not directly support or
contradict the selected node.

IRRELEVANT
The document does not materially bear on the selected node.

INSUFFICIENT
The document may be related, but the available text is insufficient to
make a defensible evidential judgement.

Rules:

1. Do not invent facts.
2. Do not infer causality merely because two events occurred near each
   other in time.
3. For SUPPORTS or CONTRADICTS, provide a short exact quote from the
   supplied document.
4. The quote must appear in the supplied document text.
5. Keep the proposition atomic and factual.
6. Return JSON only.

Return:

{
  "relation": "supports|contradicts|context|irrelevant|insufficient",
  "proposition": "atomic factual proposition or null",
  "source_quote": "exact source quote or null",
  "rationale": "brief explanation"
}
""".strip()


def _hash(value: str) -> str:
    return sha1(
        value.encode("utf-8")
    ).hexdigest()[:12]


def _normalise_text(
    value: str,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip().casefold()


def _parse_as_of(
    value: str,
) -> datetime:
    """
    The current UI supplies a calendar date.

    Until intraday time travel exists, interpret that as
    an end-of-day UTC historical cutoff and preserve that
    fact in execution provenance.
    """

    if "T" in value:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed

    parsed_date = date.fromisoformat(
        value
    )

    return datetime.combine(
        parsed_date,
        time.max,
        tzinfo=timezone.utc,
    )


def _task_kind(
    text: str,
) -> ResearchTaskKind:
    lower = text.casefold()

    if any(
        term in lower
        for term in (
            "sec filing",
            "8-k",
            "10-k",
            "10-q",
            "filing",
        )
    ):
        return (
            ResearchTaskKind
            .PRIMARY_DISCLOSURES
        )

    if any(
        term in lower
        for term in (
            "news",
            "press release",
            "announcement",
            "event",
        )
    ):
        return (
            ResearchTaskKind
            .RECENT_NEWS
        )

    return (
        ResearchTaskKind
        .SHARED_CONTEXT
    )


def _source_preferences(
    kind: ResearchTaskKind,
) -> tuple[
    ResearchSourceClass,
    ...
]:
    if (
        kind
        == ResearchTaskKind.PRIMARY_DISCLOSURES
    ):
        return (
            ResearchSourceClass.SEC_EDGAR,
            ResearchSourceClass.COMPANY_IR,
            ResearchSourceClass.NEWS,
        )

    if (
        kind
        == ResearchTaskKind.RECENT_NEWS
    ):
        return (
            ResearchSourceClass.NEWS,
            ResearchSourceClass.COMPANY_IR,
            ResearchSourceClass.SEC_EDGAR,
        )

    return (
        ResearchSourceClass.NEWS,
        ResearchSourceClass.MARKET_CONTEXT,
        ResearchSourceClass.COMPANY_IR,
    )


def _make_llm(
    target_id: str,
) -> tuple[
    OpenAICompatibleProvider,
    object,
]:
    target = get_target(
        target_id
    )

    api_key = None

    if target.api_key_env:
        api_key = os.getenv(
            target.api_key_env
        )

        if not api_key:
            raise RuntimeError(
                "Missing API key environment "
                f"variable: {target.api_key_env}"
            )

    llm = OpenAICompatibleProvider(
        provider_name=
            target.provider,

        model_name=
            target.model_name,

        base_url=
            target.base_url,

        api_key=
            api_key,

        prepend_no_think=
            target.prepend_no_think,

        use_json_response_format=
            target.use_json_response_format,

        token_limit_field=
            target.token_limit_field,

        temperature=
            target.temperature,
    )

    return llm, target


def _assess_document(
    *,
    llm: OpenAICompatibleProvider,
    pair: str,
    as_of: str,
    node_kind: str,
    node_label: str,
    document,
) -> DocumentAssessment:

    # Bound the prompt size for the MVP.
    source_text = document.text[
        :12000
    ]

    raw = llm.complete_json(
        system=
            ASSESSMENT_SYSTEM_PROMPT,

        user=f"""
Pair: {pair}
Historical cutoff: {as_of}

Selected ClaimGraph node type:
{node_kind}

Selected ClaimGraph node:
{node_label}

SOURCE DOCUMENT

Title:
{document.title}

Publisher:
{document.publisher or "unknown"}

Published:
{
    document.published_at.isoformat()
    if document.published_at
    else "unknown"
}

Text:
{source_text}
""".strip(),

        reasoning=False,
    )

    assessment = (
        DocumentAssessment
        .model_validate(raw)
    )

    # A support/contradiction claim is not admitted
    # unless its quoted span is actually present.
    if assessment.relation in {
        "supports",
        "contradicts",
    }:
        quote = (
            assessment.source_quote
            or ""
        )

        if (
            not quote
            or _normalise_text(quote)
            not in _normalise_text(
                document.text
            )
        ):
            return DocumentAssessment(
                relation="insufficient",

                proposition=None,

                source_quote=None,

                rationale=(
                    "The model proposed an evidential "
                    "relationship but its quoted source "
                    "span could not be validated against "
                    "the retrieved document."
                ),
            )

    return assessment


class ResearchNodeService:
    """
    Human-triggered follow-up research.

    BookReader is executed first.

    Open-web retrieval is attempted second and failure
    does not discard corpus results.
    """

    def research(
        self,
        *,
        target_id: str,
        pair: str,
        as_of: str,
        node: dict,
    ) -> dict:

        node_id = str(
            node["node_id"]
        )

        node_kind = str(
            node["kind"]
        )

        node_label = str(
            node["label"]
        )

        entities = tuple(
            item
            for item in pair.split("/")
            if item
        )

        cutoff = _parse_as_of(
            as_of
        )

        task_kind = _task_kind(
            node_label
        )

        digest = _hash(
            f"{pair}|{as_of}|"
            f"{node_id}|{node_label}"
        )

        task = ResearchTask(
            task_id=
                f"TASK-{digest}",

            kind=
                task_kind,

            entities=
                entities,

            question=
                node_label,

            rationale=(
                "Human-triggered follow-up "
                "research on ClaimGraph node "
                f"{node_id}."
            ),

            source_preferences=
                _source_preferences(
                    task_kind
                ),

            lookback_days=45,

            priority=1,
        )

        plan = ResearchPlan(
            plan_id=
                f"PLAN-{digest}",

            anomaly_id=
                f"ANOMALY-{pair}",

            as_of=
                cutoff,

            tasks=(
                task,
            ),
        )

        retrieved_at = datetime.now(
            timezone.utc
        )


        # =================================================
        # 1. PRIVATE CORPUS FIRST
        # =================================================

        bookreader_bundle = (
            execute_research_plan(
                plan,

                search_provider=
                    CorpusSearchProvider(),

                document_fetcher=
                    CorpusDocumentFetcher(),

                retrieved_at=
                    retrieved_at,

                per_task_limit=3,
            )
        )


        # =================================================
        # 2. OPEN WEB SECOND
        #
        # A web failure must not erase private-corpus
        # retrieval.
        # =================================================

        web_bundle = None
        web_error = None

        try:
            web_bundle = (
                execute_research_plan(
                    plan,

                    search_provider=
                        SearxngSearchProvider(),

                    document_fetcher=
                        TrafilaturaDocumentFetcher(),

                    retrieved_at=
                        retrieved_at,

                    per_task_limit=2,
                )
            )

        except Exception as exc:
            web_error = str(exc)


        bundles = [
            bookreader_bundle,
        ]

        if web_bundle is not None:
            bundles.append(
                web_bundle
            )


        documents = []

        seen_urls: set[str] = set()

        provider_by_document: dict[
            str,
            str,
        ] = {}

        records = []

        for bundle in bundles:

            records.extend(
                bundle.records
            )

            for record in bundle.records:
                if record.document_id:
                    provider_by_document[
                        record.document_id
                    ] = record.provider

            for document in bundle.documents:

                url = str(
                    document.url
                )

                if url in seen_urls:
                    continue

                seen_urls.add(url)

                documents.append(
                    document
                )


        # =================================================
        # 3. ASSESS RETRIEVED MATERIAL
        # =================================================

        llm, target = _make_llm(
            target_id
        )


        patch_nodes: list[dict] = []
        patch_edges: list[dict] = []


        action_id = (
            f"ACTION-RESEARCH-{digest}"
        )

        patch_nodes.append(
            {
                "node_id":
                    action_id,

                "kind":
                    "agent_action",

                "label":
                    "Research selected node",

                "target_node_id":
                    node_id,

                "as_of":
                    as_of,

                "as_of_resolution":
                    "calendar_date",

                "bookreader_documents":
                    len(
                        bookreader_bundle
                        .documents
                    ),

                "web_documents":
                    (
                        len(web_bundle.documents)
                        if web_bundle
                        else 0
                    ),

                "web_error":
                    web_error,
            }
        )

        patch_edges.append(
            {
                "edge_id":
                    f"E-{node_id}-{action_id}",

                "source":
                    node_id,

                "target":
                    action_id,

                "kind":
                    "triggered_research",

                "data": {},
            }
        )


        assessment_model_id = (
            f"MODEL-ASSESS-{digest}"
        )

        patch_nodes.append(
            {
                "node_id":
                    assessment_model_id,

                "kind":
                    "model_run",

                "label":
                    "Evidence assessment",

                "provider":
                    target.provider,

                "model":
                    target.model_name,

                "target_id":
                    target.id,

                "role":
                    "evidence assessment",
            }
        )

        patch_edges.append(
            {
                "edge_id":
                    f"E-{action_id}-"
                    f"{assessment_model_id}",

                "source":
                    action_id,

                "target":
                    assessment_model_id,

                "kind":
                    "invoked_model",

                "data": {},
            }
        )


        # Provider/tool execution nodes.
        provider_counts = Counter(
            record.provider
            for record in records
        )

        tool_ids: dict[
            str,
            str,
        ] = {}

        for provider, count in (
            provider_counts.items()
        ):
            tool_id = (
                f"TOOL-{provider}-"
                f"{digest}"
            )

            tool_ids[
                provider
            ] = tool_id

            patch_nodes.append(
                {
                    "node_id":
                        tool_id,

                    "kind":
                        "tool_call",

                    "label":
                        f"{provider} retrieval",

                    "provider":
                        provider,

                    "record_count":
                        count,

                    "question":
                        node_label,
                }
            )

            patch_edges.append(
                {
                    "edge_id":
                        f"E-{action_id}-"
                        f"{tool_id}",

                    "source":
                        action_id,

                    "target":
                        tool_id,

                    "kind":
                        "invoked_tool",

                    "data": {},
                }
            )


        source_ids: set[str] = set()


        for document in documents:

            provider = (
                provider_by_document.get(
                    document.document_id,
                    "unknown",
                )
            )

            document_digest = _hash(
                document.document_id
            )

            document_node_id = (
                f"DOC-{document_digest}"
            )

            source_key = (
                f"{provider}|"
                f"{document.publisher or 'unknown'}"
            )

            source_node_id = (
                f"SOURCE-{_hash(source_key)}"
            )


            if (
                source_node_id
                not in source_ids
            ):
                source_ids.add(
                    source_node_id
                )

                patch_nodes.append(
                    {
                        "node_id":
                            source_node_id,

                        "kind":
                            "source",

                        "label":
                            (
                                document.publisher
                                or provider
                            ),

                        "provider":
                            provider,
                    }
                )


            patch_nodes.append(
                {
                    "node_id":
                        document_node_id,

                    "kind":
                        "document",

                    "label":
                        document.title,

                    "document_id":
                        document.document_id,

                    "publisher":
                        document.publisher,

                    "url":
                        str(
                            document.url
                        ),

                    "published_at":
                        (
                            document
                            .published_at
                            .isoformat()
                            if document.published_at
                            else None
                        ),

                    "published_date_only":
                        document
                        .published_date_only,

                    "lineage_id":
                        document.lineage_id,
                }
            )


            patch_edges.append(
                {
                    "edge_id":
                        f"E-{source_node_id}-"
                        f"{document_node_id}",

                    "source":
                        source_node_id,

                    "target":
                        document_node_id,

                    "kind":
                        "provides",

                    "data": {},
                }
            )


            tool_id = tool_ids.get(
                provider
            )

            if tool_id:
                patch_edges.append(
                    {
                        "edge_id":
                            f"E-{tool_id}-"
                            f"{document_node_id}",

                        "source":
                            tool_id,

                        "target":
                            document_node_id,

                        "kind":
                            "retrieved",

                        "data": {},
                    }
                )


            assessment = (
                _assess_document(
                    llm=llm,

                    pair=pair,

                    as_of=as_of,

                    node_kind=
                        node_kind,

                    node_label=
                        node_label,

                    document=
                        document,
                )
            )


            if assessment.relation in {
                "supports",
                "contradicts",
            }:

                evidence_id = (
                    f"EVIDENCE-"
                    f"{document_digest}-"
                    f"{_hash(node_id)}"
                )

                evidence_kind = (
                    "evidence"
                    if assessment.relation
                    == "supports"
                    else "counter_evidence"
                )

                patch_nodes.append(
                    {
                        "node_id":
                            evidence_id,

                        "kind":
                            evidence_kind,

                        "label":
                            (
                                assessment.proposition
                                or assessment.rationale
                            ),

                        "source_quote":
                            assessment.source_quote,

                        "rationale":
                            assessment.rationale,

                        "document_id":
                            document.document_id,

                        "epistemic_status":
                            "source_validated",
                    }
                )

                patch_edges.append(
                    {
                        "edge_id":
                            f"E-{document_node_id}-"
                            f"{evidence_id}",

                        "source":
                            document_node_id,

                        "target":
                            evidence_id,

                        "kind":
                            "contains",

                        "data": {},
                    }
                )

                relation_edge = (
                    "satisfies_requirement"
                    if (
                        node_kind
                        == "evidence_requirement"
                        and assessment.relation
                        == "supports"
                    )
                    else assessment.relation
                )

                patch_edges.append(
                    {
                        "edge_id":
                            f"E-{evidence_id}-"
                            f"{node_id}",

                        "source":
                            evidence_id,

                        "target":
                            node_id,

                        "kind":
                            relation_edge,

                        "data": {},
                    }
                )

                patch_edges.append(
                    {
                        "edge_id":
                            f"E-{assessment_model_id}-"
                            f"{evidence_id}",

                        "source":
                            assessment_model_id,

                        "target":
                            evidence_id,

                        "kind":
                            "assessed",

                        "data": {},
                    }
                )


            elif (
                assessment.relation
                == "context"
            ):
                patch_edges.append(
                    {
                        "edge_id":
                            f"E-{document_node_id}-"
                            f"{node_id}",

                        "source":
                            document_node_id,

                        "target":
                            node_id,

                        "kind":
                            "contextualizes",

                        "data": {},
                    }
                )


        return {
            "patch_id":
                f"PATCH-{digest}",

            "target_node_id":
                node_id,

            "new_nodes":
                patch_nodes,

            "new_edges":
                patch_edges,

            "retrieval_summary": {
                "bookreader_documents":
                    len(
                        bookreader_bundle
                        .documents
                    ),

                "web_documents":
                    (
                        len(web_bundle.documents)
                        if web_bundle
                        else 0
                    ),

                "web_error":
                    web_error,

                "total_documents":
                    len(documents),
            },
        }
