from __future__ import annotations

from datetime import datetime
from hashlib import sha1

from financial_assistant.domain import (
    SourceDocument,
)

from financial_assistant.research import (
    ResearchPlan,
)

from .interfaces import (
    DocumentFetcher,
    SearchProvider,
)

from .models import (
    RetrievalBundle,
    RetrievalRecord,
    RetrievalStatus,
    SearchHit,
)

from .queries import (
    build_search_query,
)


def _record_id(
    plan_id: str,
    hit_id: str,
    task_id: str,
) -> str:
    raw = (
        f"{plan_id}|"
        f"{task_id}|"
        f"{hit_id}"
    )

    digest = sha1(
        raw.encode("utf-8")
    ).hexdigest()[:12]

    return f"RET-{digest}"


def execute_research_plan(
    plan: ResearchPlan,
    *,
    search_provider: SearchProvider,
    document_fetcher: DocumentFetcher,
    retrieved_at: datetime,
    per_task_limit: int = 3,
) -> RetrievalBundle:
    """
    Execute a ResearchPlan while preserving both:

    epistemic provenance:
        which documents became available?

    execution provenance:
        which queries were run?
        which hits were filtered?
        which documents failed?
        which URLs were reused?

    Known future documents are excluded from the
    evidence corpus.
    """

    if per_task_limit < 1:
        raise ValueError(
            "per_task_limit must be >= 1"
        )

    all_hits: list[SearchHit] = []

    documents: list[
        SourceDocument
    ] = []

    records: list[
        RetrievalRecord
    ] = []

    # URL-level cache prevents repeatedly fetching the
    # same document when multiple research tasks find it.
    document_by_url: dict[
        str,
        SourceDocument,
    ] = {}

    for task in plan.tasks:
        query = build_search_query(
            task
        )

        hits = search_provider.search(
            query,
            task_id=task.task_id,
            limit=per_task_limit,
        )

        for hit in hits:
            if hit.task_id != task.task_id:
                raise ValueError(
                    f"Search provider returned hit "
                    f"{hit.hit_id} for task "
                    f"{hit.task_id}, expected "
                    f"{task.task_id}"
                )

            all_hits.append(
                hit
            )

            record_id = _record_id(
                plan.plan_id,
                hit.hit_id,
                task.task_id,
            )

            # Point-in-time guardrail:
            #
            # if we KNOW this source was published
            # after the investigation cutoff, it must
            # not become evidence.
            if (
                hit.published_at is not None
                and hit.published_at > plan.as_of
            ):
                records.append(
                    RetrievalRecord(
                        record_id=record_id,
                        task_id=task.task_id,
                        hit_id=hit.hit_id,
                        provider=hit.provider,
                        query=hit.query,
                        retrieved_at=retrieved_at,
                        status=(
                            RetrievalStatus
                            .FILTERED_FUTURE
                        ),
                        note=(
                            "Known publication time "
                            "is after investigation "
                            "as_of cutoff."
                        ),
                    )
                )

                continue

            url_key = str(
                hit.url
            )

            # Same URL found by another task:
            # preserve this retrieval event but avoid
            # downloading the document again.
            if url_key in document_by_url:
                document = (
                    document_by_url[
                        url_key
                    ]
                )

                records.append(
                    RetrievalRecord(
                        record_id=record_id,
                        task_id=task.task_id,
                        hit_id=hit.hit_id,
                        provider=hit.provider,
                        query=hit.query,
                        retrieved_at=retrieved_at,
                        status=(
                            RetrievalStatus.REUSED
                        ),
                        document_id=(
                            document.document_id
                        ),
                        note=(
                            "Document reused from "
                            "earlier URL retrieval."
                        ),
                    )
                )

                continue

            try:
                document = (
                    document_fetcher.fetch(
                        hit,
                        retrieved_at=(
                            retrieved_at
                        ),
                    )
                )

            except Exception as exc:
                records.append(
                    RetrievalRecord(
                        record_id=record_id,
                        task_id=task.task_id,
                        hit_id=hit.hit_id,
                        provider=hit.provider,
                        query=hit.query,
                        retrieved_at=retrieved_at,
                        status=(
                            RetrievalStatus.FAILED
                        ),
                        note=(
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    )
                )

                continue

            document_by_url[
                url_key
            ] = document

            documents.append(
                document
            )

            records.append(
                RetrievalRecord(
                    record_id=record_id,
                    task_id=task.task_id,
                    hit_id=hit.hit_id,
                    provider=hit.provider,
                    query=hit.query,
                    retrieved_at=retrieved_at,
                    status=(
                        RetrievalStatus.FETCHED
                    ),
                    document_id=(
                        document.document_id
                    ),
                )
            )

    return RetrievalBundle(
        plan_id=plan.plan_id,
        as_of=plan.as_of,

        hits=tuple(
            all_hits
        ),

        documents=tuple(
            documents
        ),

        records=tuple(
            records
        ),
    )
