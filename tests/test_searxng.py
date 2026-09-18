import json

from unittest.mock import patch

from financial_assistant.retrieval import (
    SearxngSearchProvider,
)


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False

    def read(self):
        return json.dumps(
            {
                "query":
                    "AAA company news",

                "results": [
                    {
                        "title":
                            "AAA announces "
                            "new restrictions",

                        "url":
                            "https://example.com/"
                            "article-1",

                        "content":
                            "Illustrative snippet.",

                        "publishedDate":
                            "2026-09-16T08:00:00",

                        "engine":
                            "brave",

                        "engines": [
                            "brave",
                            "duckduckgo",
                        ],
                    },

                    {
                        "title":
                            "AAA investor relations",

                        "url":
                            "https://aaa.example/"
                            "investors",

                        "content":
                            "Investor relations.",

                        "publishedDate":
                            None,

                        "engine":
                            "duckduckgo",
                    },
                ],

                "unresponsive_engines": [],
            }
        ).encode("utf-8")


@patch(
    "financial_assistant."
    "retrieval.searxng.urlopen"
)
def test_searxng_returns_structured_hits(
    mock_urlopen,
):
    mock_urlopen.return_value = (
        FakeResponse()
    )

    provider = (
        SearxngSearchProvider()
    )

    hits = provider.search(
        "AAA company news",
        task_id="TASK-AAA",
        limit=5,
    )

    assert len(hits) == 2

    first = hits[0]

    assert first.task_id == (
        "TASK-AAA"
    )

    assert first.provider == (
        "searxng"
    )

    assert first.publisher == (
        "example.com"
    )

    assert first.title == (
        "AAA announces "
        "new restrictions"
    )

    assert first.published_at.year == (
        2026
    )

    second = hits[1]

    # Missing search metadata stays missing.
    assert second.published_at is None


@patch(
    "financial_assistant."
    "retrieval.searxng.urlopen"
)
def test_searxng_respects_limit(
    mock_urlopen,
):
    mock_urlopen.return_value = (
        FakeResponse()
    )

    provider = (
        SearxngSearchProvider()
    )

    hits = provider.search(
        "AAA company news",
        task_id="TASK-AAA",
        limit=1,
    )

    assert len(hits) == 1
