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


from collections import Counter


from .query_expansion import (
    QueryExpander,
    QueryExpansion,
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



def _is_known_future(
    *,
    published_at: datetime | None,
    published_date_only: bool,
    as_of: datetime,
) -> bool:
    """
    True only when publication is definitely later
    than the historical cutoff.

    Date-only metadata on the SAME calendar date is
    unresolved rather than assumed to be midnight.
    """

    if published_at is None:
        return False

    if published_date_only:
        return (
            published_at.date()
            > as_of.date()
        )

    return (
        published_at > as_of
    )



def _select_diverse_hits(
    hit_groups: list[
        tuple[SearchHit, ...]
    ],
    *,
    limit: int,
) -> tuple[SearchHit, ...]:
    """
    Admit a bounded set of hits while encouraging
    diversity across both:

    - generated query concepts;
    - retrieval providers.

    This does NOT treat provider ranks as comparable
    evidence scores.
    """

    candidates: list[
        tuple[int, SearchHit]
    ] = []

    for query_index, hits in enumerate(
        hit_groups
    ):
        for hit in hits:
            candidates.append(
                (query_index, hit)
            )

    selected: list[SearchHit] = []

    seen_urls: set[str] = set()

    query_counts: Counter[int] = Counter()
    provider_counts: Counter[str] = Counter()

    while (
        len(selected) < limit
        and candidates
    ):
        available = [
            (query_index, hit)
            for query_index, hit in candidates
            if str(hit.url) not in seen_urls
        ]

        if not available:
            break

        query_index, hit = min(
            available,
            key=lambda item: (
                # First favour concepts that have not
                # yet contributed a candidate.
                query_counts[item[0]],

                # Then favour retrieval providers that
                # have contributed fewer candidates.
                provider_counts[
                    item[1].provider
                ],

                # Provider-local rank is only a
                # tie-breaker.
                item[1].rank,

                item[0],
            ),
        )

        selected.append(hit)

        seen_urls.add(
            str(hit.url)
        )

        query_counts[
            query_index
        ] += 1

        provider_counts[
            hit.provider
        ] += 1

    return tuple(selected)








def execute_research_plan(
    plan: ResearchPlan,
    *,
    search_provider: SearchProvider,
    document_fetcher: DocumentFetcher,
    retrieved_at: datetime,
    per_task_limit: int = 3,
    query_expander: QueryExpander | None = None,
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

    query_expansions: list[
        QueryExpansion
    ] = []


    # URL-level cache prevents repeatedly fetching the
    # same document when multiple research tasks find it.
    document_by_url: dict[
        str,
        SourceDocument,
    ] = {}

    for task in plan.tasks:
		# ---------------------------------------------
        # Build retrieval queries.
        #
        # Without an expander we preserve the original
        # deterministic behaviour.
        #
        # With an expander, several explicit retrieval
        # hypotheses compete for one fixed per-task
        # retrieval budget.
        # ---------------------------------------------

        if query_expander is None:
            query = build_search_query(
                task,
                as_of=plan.as_of,
            )

            candidate_hits = (
                search_provider.search(
                    query,
                    task_id=task.task_id,
                    limit=per_task_limit,
                    as_of=plan.as_of,
                )
            )

            hits = candidate_hits

        else:
            expansion = query_expander(
                task,
                as_of=plan.as_of,
            )

            if (
                expansion.task_id
                != task.task_id
            ):
                raise ValueError(
                    "Query expander returned "
                    f"task_id={expansion.task_id!r}; "
                    f"expected {task.task_id!r}"
                )

            query_expansions.append(
                expansion
            )

            # Never run more generated concepts than
            # the task's total retrieval budget.
            concepts = (
                expansion.queries[
                    :per_task_limit
                ]
            )

            hit_groups: list[
                tuple[SearchHit, ...]
            ] = []

            for concept in concepts:
                print(
                        "SEARCH CONCEPT:",
                        task.task_id,
                        "|",
                        concept.proximity.value,
                        "|",
                        concept.relation,
                        "|",
                        repr(concept.text),
                    )

                concept_hits = (
                    search_provider.search(
                        concept.text,
                        task_id=task.task_id,

                        # With CompositeSearchProvider
                        # this normally gives us one
                        # corpus candidate and one web
                        # candidate.
                        limit=2,

                        as_of=plan.as_of,
                    )
                )

                for hit in concept_hits:
                    if (
                        hit.task_id
                        != task.task_id
                    ):
                        raise ValueError(
                            "Search provider returned "
                            f"hit {hit.hit_id} for task "
                            f"{hit.task_id}, expected "
                            f"{task.task_id}"
                        )

                hit_groups.append(
                    concept_hits
                )

            candidate_hits = tuple(
                hit
                for group in hit_groups
                for hit in group
            )

            hits = _select_diverse_hits(
                hit_groups,
                limit=per_task_limit,
            )

        # Both retrieval paths now have:
        #
        # candidate_hits:
        #     everything returned by search
        #
        # hits:
        #     candidates admitted to the fetch budget
        #
        # In the deterministic path these are identical.
        # In the expanded path, hits may be a bounded
        # subset of candidate_hits.
        selected_hit_ids = {
            (
                hit.hit_id,
                hit.query,
                str(hit.url),
            )
            for hit in hits
        }

        # Preserve search candidates that were returned
        # but not admitted to the bounded fetch budget.
        for hit in candidate_hits:
            all_hits.append(hit)

            identity = (
                hit.hit_id,
                hit.query,
                str(hit.url),
            )

            if identity in selected_hit_ids:
                continue

            records.append(
                RetrievalRecord(
                    record_id=_record_id(
                        plan.plan_id,
                        (
                            hit.hit_id
                            + "-budget-"
                            + sha1(
                                hit.query.encode(
                                    "utf-8"
                                )
                            ).hexdigest()[:8]
                        ),
                        task.task_id,
                    ),
                    task_id=task.task_id,
                    hit_id=hit.hit_id,
                    provider=hit.provider,
                    query=hit.query,
                    retrieved_at=retrieved_at,
                    status=(
                        RetrievalStatus
                        .SKIPPED_BUDGET
                    ),
                    note=(
                        "Search candidate was not "
                        "admitted to the fixed "
                        "per-task retrieval budget."
                    ),
                )
            )
		


        for hit in hits:
            if hit.task_id != task.task_id:
                raise ValueError(
                    f"Search provider returned hit "
                    f"{hit.hit_id} for task "
                    f"{hit.task_id}, expected "
                    f"{task.task_id}"
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
            if _is_known_future(
                published_at=hit.published_at,
                published_date_only=(
                    hit.published_date_only
                ),
                as_of=plan.as_of,
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

            # Search metadata may not have exposed
            # a publication date. Re-check after the
            # actual page has been downloaded and its
            # metadata extracted.
            if _is_known_future(
                published_at=(
                    document.published_at
                ),
                published_date_only=(
                    document.published_date_only
                ),
                as_of=plan.as_of,
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
                        document_id=(
                            document.document_id
                        ),
                        note=(
                            "Publication time extracted "
                            "from document is after "
                            "investigation as_of cutoff."
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
                        RetrievalStatus
                        .FETCHED_UNDATED
                        if document.published_at
                        is None
                        else (
                            RetrievalStatus
                            .FETCHED_DATE_ONLY
                            if (
                                document
                                .published_date_only
                            )
                            else RetrievalStatus
                            .FETCHED
                        )
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

		query_expansions=tuple(
            query_expansions
        ),

        documents=tuple(
            documents
        ),

        records=tuple(
            records
        ),
    )
