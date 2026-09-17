from __future__ import annotations

import json

from datetime import (
    datetime,
    timezone,
)

from hashlib import sha1

from urllib.parse import urlparse
from urllib.request import (
    Request,
    urlopen,
)

from trafilatura import extract

from financial_assistant.domain import (
    SourceDocument,
)

from .models import SearchHit


class TrafilaturaDocumentFetcher:
    """
    Retrieve an original web page and normalize its
    main textual content into SourceDocument.

    HTTP transport uses the Python standard library.
    Trafilatura is responsible only for extracting
    meaningful article text and metadata from HTML.
    """

    name = "trafilatura"

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_bytes: int = 5_000_000,
        min_text_chars: int = 200,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.min_text_chars = min_text_chars

    def fetch(
        self,
        hit: SearchHit,
        *,
        retrieved_at: datetime,
    ) -> SourceDocument:
        request = Request(
            str(hit.url),
            headers={
                "User-Agent": (
                    "ClaimGraph/0.2 "
                    "(research prototype)"
                ),
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml"
                ),
            },
        )

        with urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:
            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                )
                .split(";", 1)[0]
                .strip()
                .lower()
            )

            if (
                content_type
                and content_type not in {
                    "text/html",
                    "application/xhtml+xml",
                }
            ):
                raise ValueError(
                    "Unsupported content type: "
                    f"{content_type}"
                )

            body = response.read(
                self.max_bytes + 1
            )

            if len(body) > self.max_bytes:
                raise ValueError(
                    "Document exceeds maximum "
                    f"size of {self.max_bytes} bytes"
                )

            final_url = response.geturl()

        extracted = extract(
            body,
            url=final_url,
            output_format="json",
            with_metadata=True,
            include_comments=False,
            include_tables=False,
        )

        if not extracted:
            raise ValueError(
                "Trafilatura could not extract "
                "document content"
            )

        payload = json.loads(
            extracted
        )

        text = (
            payload.get("text")
            or ""
        ).strip()

        if len(text) < self.min_text_chars:
            raise ValueError(
                "Extracted document is too short "
                f"({len(text)} characters)"
            )

        title = (
            payload.get("title")
            or hit.title
        )

        parsed_url = urlparse(
            final_url
        )

        publisher = (
            payload.get("sitename")
            or payload.get("hostname")
            or hit.publisher
            or parsed_url.hostname
            or "Unknown source"
        )

        (
            extracted_published_at,
            extracted_date_only,
        ) = _parse_extracted_date(
            payload.get("date")
        )

        if extracted_published_at is not None:
            published_at = (
                extracted_published_at
            )

            published_date_only = (
                extracted_date_only
            )

        else:
            published_at = (
                hit.published_at
            )

            published_date_only = (
                hit.published_date_only
            )

        # lineage identifies the underlying URL across
        # versions; document_id additionally identifies
        # this particular extracted content.
        lineage_digest = sha1(
            final_url.encode("utf-8")
        ).hexdigest()[:12]

        content_digest = sha1(
            text.encode("utf-8")
        ).hexdigest()[:12]

        return SourceDocument(
            document_id=(
                f"DOC-{lineage_digest}-"
                f"{content_digest}"
            ),

            title=title,
            publisher=publisher,
            url=final_url,

            published_at=published_at,

            published_date_only=(
                published_date_only
            ),

            retrieved_at=retrieved_at,

            text=text,

            lineage_id=(
                f"URL-{lineage_digest}"
            ),
        )


def _parse_extracted_date(
    value: str | None,
) -> tuple[
    datetime | None,
    bool,
]:
    """
    Preserve whether extracted publication metadata
    supplied a full timestamp or only a calendar date.
    """

    if not value:
        return (
            None,
            False,
        )

    raw = value.strip()

    normalized = raw.replace(
        "Z",
        "+00:00",
    )

    date_only = (
        len(raw) == 10
        and raw[4] == "-"
        and raw[7] == "-"
    )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )

    except ValueError:
        return (
            None,
            False,
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return (
        parsed,
        date_only,
    )
