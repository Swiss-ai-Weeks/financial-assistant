import io
import json

from datetime import (
    datetime,
    timezone,
)

from financial_assistant.retrieval.bookreader import (
    CorpusDocumentFetcher,
    CorpusSearchProvider,
)


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(
            payload
        ).encode("utf-8")

    def __enter__(self):
        return io.BytesIO(self._data)

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False


def test_bookreader_search_maps_hit_and_date(
    monkeypatch,
):
    payload = {
        "query": "Federal Reserve",
        "count": 1,
        "results": [
            {
                "document_id":
                    "NEWS-2026-09-17-P0001-test",
                "publication":
                    "The Wall Street Journal",
                "issue_date":
                    "2026-09-17",
                "page_number": 1,
                "score": -5.5,
                "snippet":
                    "The Federal Reserve...",
                "text": None,
            }
        ],
    }

    seen = {}

    def fake_urlopen(
        request,
        timeout,
    ):
        seen["url"] = request.full_url
        seen["authorization"] = (
            request.get_header(
                "Authorization"
            )
        )

        return FakeResponse(payload)

    monkeypatch.setattr(
        "financial_assistant.retrieval."
        "bookreader.urlopen",
        fake_urlopen,
    )

    provider = CorpusSearchProvider(
        base_url="https://bookreader.test",
        api_token="secret",
        lookback_days=45,
    )

    hits = provider.search(
        "Federal Reserve",
        task_id="TASK-1",
        limit=3,
        as_of=datetime(
            2026,
            9,
            17,
            15,
            30,
            tzinfo=timezone.utc,
        ),
    )

    assert len(hits) == 1

    hit = hits[0]

    assert hit.provider == "bookreader"
    assert hit.publisher == (
        "The Wall Street Journal"
    )
    assert hit.published_date_only is True
    assert hit.published_at.date().isoformat() == (
        "2026-09-17"
    )

    assert "to_date=2026-09-17" in seen["url"]
    assert "from_date=2026-08-03" in seen["url"]

    assert seen["authorization"] == (
        "Bearer secret"
    )


def test_bookreader_fetch_maps_document(
    monkeypatch,
):
    payload = {
        "rowid": 4217,
        "document_id":
            "NEWS-2026-09-17-P0001-test",
        "publication":
            "The Wall Street Journal",
        "issue_date":
            "2026-09-17",
        "page_number": 1,
        "source_pdf":
            "/private/path/wsj.pdf",
        "source_sha256":
            "abc123",
        "text":
            "Federal Reserve article text.",
    }

    def fake_urlopen(
        request,
        timeout,
    ):
        return FakeResponse(payload)

    monkeypatch.setattr(
        "financial_assistant.retrieval."
        "bookreader.urlopen",
        fake_urlopen,
    )

    provider = CorpusSearchProvider(
        base_url="https://bookreader.test",
        api_token="secret",
    )

    # Build the hit through the provider-shaped model
    # rather than constructing unrelated metadata.
    from financial_assistant.retrieval.models import (
        SearchHit,
    )

    hit = SearchHit(
        hit_id="TASK-1:bookreader:test",
        task_id="TASK-1",
        provider="bookreader",
        query="Federal Reserve",
        rank=1,
        title=(
            "The Wall Street Journal — "
            "2026-09-17 — page 1"
        ),
        url=(
            "https://bookreader.test/documents/"
            "NEWS-2026-09-17-P0001-test"
        ),
        snippet="Federal Reserve...",
        publisher="The Wall Street Journal",
        published_at=datetime(
            2026,
            9,
            17,
            tzinfo=timezone.utc,
        ),
        published_date_only=True,
    )

    fetcher = CorpusDocumentFetcher(
        base_url="https://bookreader.test",
        api_token="secret",
    )

    retrieved_at = datetime(
        2026,
        9,
        19,
        10,
        0,
        tzinfo=timezone.utc,
    )

    document = fetcher.fetch(
        hit,
        retrieved_at=retrieved_at,
    )

    assert document.document_id == (
        "NEWS-2026-09-17-P0001-test"
    )

    assert document.publisher == (
        "The Wall Street Journal"
    )

    assert document.published_date_only is True
    assert document.text == (
        "Federal Reserve article text."
    )

    assert document.lineage_id == "abc123"
    assert document.retrieved_at == retrieved_at
