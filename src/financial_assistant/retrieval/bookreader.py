from __future__ import annotations

import json
import os

from datetime import (
    date,
    datetime,
    time,
    timedelta,
    timezone,
)

from hashlib import sha1

from urllib.parse import (
    quote,
    unquote,
    urlencode,
    urlparse,
)

from urllib.request import (
    Request,
    urlopen,
)

from financial_assistant.domain import (
    SourceDocument,
)

from .models import SearchHit


def _date_carrier(value: str) -> datetime:
    """
    Convert YYYY-MM-DD into a UTC-midnight datetime.

    Midnight is only a carrier for the known calendar
    date. Callers must preserve published_date_only=True.
    """
    parsed = date.fromisoformat(value)

    return datetime.combine(
        parsed,
        time.min,
        tzinfo=timezone.utc,
    )


def _title(
    publication: str,
    issue_date: str,
    page_number: int,
) -> str:
    return (
        f"{publication} — "
        f"{issue_date} — "
        f"page {page_number}"
    )


class _BookReaderClient:
    """
    Small authenticated JSON client shared by search
    and document retrieval.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.base_url = (
            base_url
            or os.getenv("BOOKREADER_BASE_URL")
            or ""
        ).rstrip("/")

        self.api_token = (
            api_token
            or os.getenv("BOOKREADER_API_TOKEN")
            or ""
        )

        self.timeout_seconds = timeout_seconds

        if not self.base_url:
            raise ValueError(
                "BOOKREADER_BASE_URL is required"
            )

        if not self.api_token:
            raise ValueError(
                "BOOKREADER_API_TOKEN is required"
            )

    def get_json(
        self,
        url: str,
    ) -> dict:
        request = Request(
            url,
            headers={
                "Authorization": (
                    f"Bearer {self.api_token}"
                ),
                "Accept": "application/json",
                "User-Agent": (
                    "ClaimGraph/0.2 "
                    "(BookReader adapter)"
                ),
            },
        )

        with urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:
            return json.load(response)


class CorpusSearchProvider(_BookReaderClient):
    """
    SearchProvider backed by the private BookReader
    newspaper corpus.

    BookReader performs discovery over a bounded corpus.
    Returned hits are not yet evidence.

    When as_of is supplied, the provider performs
    point-in-time filtering at search time so future
    documents do not consume the top-N result slots.
    """

    name = "bookreader"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float = 10.0,
        lookback_days: int | None = 45,
    ):
        super().__init__(
            base_url=base_url,
            api_token=api_token,
            timeout_seconds=timeout_seconds,
        )

        if (
            lookback_days is not None
            and lookback_days < 0
        ):
            raise ValueError(
                "lookback_days must be >= 0"
            )

        self.lookback_days = lookback_days

    def search(
        self,
        query: str,
        *,
        task_id: str,
        limit: int = 5,
        as_of: datetime | None = None,
    ) -> tuple[SearchHit, ...]:
        if limit < 1:
            raise ValueError(
                "limit must be >= 1"
            )

        params: dict[str, str | int] = {
            "q": query,
            "limit": limit,
        }

        if as_of is not None:
            to_date = as_of.date()

            params["to_date"] = (
                to_date.isoformat()
            )

            if self.lookback_days is not None:
                from_date = (
                    to_date
                    - timedelta(
                        days=self.lookback_days
                    )
                )

                params["from_date"] = (
                    from_date.isoformat()
                )

        url = (
            f"{self.base_url}/search?"
            f"{urlencode(params)}"
        )

        payload = self.get_json(url)

        results = payload.get("results") or []

        hits: list[SearchHit] = []

        for rank, result in enumerate(
            results,
            start=1,
        ):
            document_id = result.get(
                "document_id"
            )
            publication = result.get(
                "publication"
            )
            issue_date = result.get(
                "issue_date"
            )
            page_number = result.get(
                "page_number"
            )

            if (
                not document_id
                or not publication
                or not issue_date
                or page_number is None
            ):
                continue

            document_url = (
                f"{self.base_url}/documents/"
                f"{quote(document_id, safe='')}"
            )

            digest = sha1(
                document_id.encode("utf-8")
            ).hexdigest()[:12]

            hits.append(
                SearchHit(
                    hit_id=(
                        f"{task_id}:"
                        f"bookreader:{digest}"
                    ),
                    task_id=task_id,
                    provider=self.name,
                    query=query,
                    rank=rank,
                    title=_title(
                        publication,
                        issue_date,
                        int(page_number),
                    ),
                    url=document_url,
                    snippet=(
                        result.get("snippet")
                        or ""
                    ),
                    publisher=publication,
                    published_at=(
                        _date_carrier(
                            issue_date
                        )
                    ),
                    published_date_only=True,
                )
            )

        return tuple(hits)


class CorpusDocumentFetcher(_BookReaderClient):
    """
    Turn a BookReader SearchHit into an evidence-bearing
    SourceDocument.

    Unlike Trafilatura, no HTML extraction is required:
    BookReader already provides normalized page text.
    """

    name = "bookreader"

    def fetch(
        self,
        hit: SearchHit,
        *,
        retrieved_at: datetime,
    ) -> SourceDocument:
        if hit.provider != "bookreader":
            raise ValueError(
                "CorpusDocumentFetcher can only "
                "fetch BookReader hits"
            )

        parsed = urlparse(
            str(hit.url)
        )

        prefix = "/documents/"

        if prefix not in parsed.path:
            raise ValueError(
                "BookReader hit URL does not "
                "contain a document identifier"
            )

        document_id = unquote(
            parsed.path.split(
                prefix,
                1,
            )[1]
        )

        payload = self.get_json(
            str(hit.url)
        )

        returned_id = payload.get(
            "document_id"
        )

        if returned_id != document_id:
            raise ValueError(
                "BookReader document identifier "
                "does not match requested document"
            )

        publication = (
            payload.get("publication")
            or hit.publisher
            or "Unknown publication"
        )

        issue_date = payload.get(
            "issue_date"
        )

        page_number = payload.get(
            "page_number"
        )

        text = (
            payload.get("text")
            or ""
        ).strip()

        if not issue_date:
            raise ValueError(
                "BookReader document has no "
                "issue_date"
            )

        if page_number is None:
            raise ValueError(
                "BookReader document has no "
                "page_number"
            )

        if not text:
            raise ValueError(
                "BookReader document has no text"
            )

        return SourceDocument(
            document_id=document_id,
            title=_title(
                publication,
                issue_date,
                int(page_number),
            ),
            publisher=publication,
            url=hit.url,
            published_at=(
                _date_carrier(
                    issue_date
                )
            ),
            published_date_only=True,
            retrieved_at=retrieved_at,
            text=text,
            lineage_id=(
                payload.get("source_sha256")
                or document_id
            ),
        )
