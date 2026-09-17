from datetime import (
    datetime,
    timezone,
)

from unittest.mock import patch

from financial_assistant.retrieval import (
    SearchHit,
    TrafilaturaDocumentFetcher,
)


NOW = datetime(
    2026,
    9,
    17,
    7,
    30,
    tzinfo=timezone.utc,
)


HTML = b"""
<html>
<head>
  <title>AAA Export Rule Update</title>
  <meta
    property="article:published_time"
    content="2026-09-16T08:00:00+00:00"
  />
</head>
<body>
<article>
  <h1>AAA Export Rule Update</h1>

  <p>
    AAA said new export rules could restrict
    shipments of several affected products.
    Management said it is reviewing the scope
    of the restrictions and their potential
    impact on customers and operations.
  </p>

  <p>
    The company did not quantify the potential
    revenue impact in the announcement. Further
    information is expected in subsequent company
    disclosures and regulatory filings.
  </p>
</article>
</body>
</html>
"""


class FakeResponse:
    headers = {
        "Content-Type":
            "text/html; charset=utf-8"
    }

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False

    def read(self, size=-1):
        return HTML[:size]

    def geturl(self):
        return (
            "https://example.com/"
            "aaa-export-rule"
        )


@patch(
    "financial_assistant."
    "retrieval.fetchers.urlopen"
)
def test_fetcher_creates_source_document(
    mock_urlopen,
):
    mock_urlopen.return_value = (
        FakeResponse()
    )

    hit = SearchHit(
        hit_id="HIT-1",
        task_id="TASK-1",
        provider="searxng",
        query="AAA recent company news",
        rank=1,
        title="Search result title",
        url=(
            "https://example.com/"
            "aaa-export-rule"
        ),
        publisher="example.com",
    )

    fetcher = (
        TrafilaturaDocumentFetcher()
    )

    document = fetcher.fetch(
        hit,
        retrieved_at=NOW,
    )

    assert document.title

    assert (
        "export rules"
        in document.text.lower()
    )

    assert len(document.text) > 200

    assert document.lineage_id.startswith(
        "URL-"
    )

    assert document.document_id.startswith(
        "DOC-"
    )

    assert document.retrieved_at == NOW
