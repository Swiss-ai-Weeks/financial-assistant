from datetime import (
    datetime,
    timezone,
)

import pytest

from pydantic import ValidationError

from financial_assistant.domain import (
    SourceDocument,
)

from financial_assistant.llm import (
    extract_claims,
)


NOW = datetime(
    2026,
    9,
    17,
    tzinfo=timezone.utc,
)


DOCUMENT = SourceDocument(
    document_id="DOC-TEST",
    title="Test source",
    publisher="Example",
    url="https://example.com/article",
    published_at=NOW,
    retrieved_at=NOW,
    text=(
        "NVIDIA reported revenue of $68.1 billion "
        "for the fourth quarter, up 73% from a year ago."
    ),
)


class GoodProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def complete_json(
        self,
        *,
        system,
        user,
        reasoning=False,
    ):
        return {
            "claims": [
                {
                    "text": (
                        "NVIDIA reported revenue "
                        "of $68.1 billion for the "
                        "fourth quarter."
                    ),

                    "claim_type":
                        "reported_fact",

                    "source_quote": (
                        "NVIDIA reported revenue "
                        "of $68.1 billion for the "
                        "fourth quarter"
                    ),
                }
            ]
        }


class InvalidTypeProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def complete_json(
        self,
        *,
        system,
        user,
        reasoning=False,
    ):
        return {
            "claims": [
                {
                    "text": (
                        "NVIDIA reported revenue "
                        "of $68.1 billion."
                    ),

                    "claim_type":
                        "financial_performance",

                    "source_quote": (
                        "NVIDIA reported revenue "
                        "of $68.1 billion"
                    ),
                }
            ]
        }


class FakeQuoteProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def complete_json(
        self,
        *,
        system,
        user,
        reasoning=False,
    ):
        return {
            "claims": [
                {
                    "text":
                        "Revenue was materially strong.",

                    "claim_type":
                        "interpretation",

                    "source_quote":
                        "Revenue was materially strong.",
                }
            ]
        }


def test_valid_claim_is_accepted():
    run, claims = extract_claims(
        DOCUMENT,
        GoodProvider(),
    )

    assert len(claims) == 1

    assert (
        claims[0].source_quote
        in DOCUMENT.text
    )

    assert (
        claims[0].model_run_id
        == run.run_id
    )


def test_invalid_claim_type_is_rejected():
    with pytest.raises(
        ValidationError,
    ):
        extract_claims(
            DOCUMENT,
            InvalidTypeProvider(),
        )


def test_invented_source_quote_is_rejected():
    with pytest.raises(
        ValueError,
        match="exact source span",
    ):
        extract_claims(
            DOCUMENT,
            FakeQuoteProvider(),
        )


def test_straight_quote_can_resolve_to_exact_source_span():
    from financial_assistant.llm.claim_extraction import (
        _resolve_source_quote,
    )

    source = (
        "“Computing demand is growing exponentially — "
        "the agentic AI inflection point has arrived."
    )

    proposed = (
        '"Computing demand is growing exponentially — '
        "the agentic AI inflection point has arrived."
    )

    resolved = _resolve_source_quote(
        proposed,
        source,
    )

    assert (
        resolved
        == "Computing demand is growing exponentially — "
        "the agentic AI inflection point has arrived."
    )

    assert resolved in source


def test_only_as_many_claims_are_requested_as_will_be_kept():
    class Spy:
        provider_name = "fake"
        model_name = "fake-model"
        system = None

        def complete_json(self, *, system, user, reasoning=False):
            Spy.system = system

            return {"claims": []}

    extract_claims(DOCUMENT, Spy(), max_claims=3)

    assert "Extract at most 3 claims" in Spy.system
    assert "{max_claims}" not in Spy.system
