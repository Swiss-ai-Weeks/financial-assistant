from datetime import (
    datetime,
    timezone,
)

from financial_assistant.retrieval.fetchers import (
    _parse_extracted_date,
)

from financial_assistant.retrieval.searxng import (
    _parse_published_date,
)


def test_search_date_only_is_preserved():
    published_at, date_only = (
        _parse_published_date(
            "2026-02-27"
        )
    )

    assert published_at == datetime(
        2026,
        2,
        27,
        tzinfo=timezone.utc,
    )

    assert date_only is True


def test_search_precise_timestamp_is_preserved():
    published_at, date_only = (
        _parse_published_date(
            "2026-02-27T15:30:00Z"
        )
    )

    assert published_at == datetime(
        2026,
        2,
        27,
        15,
        30,
        tzinfo=timezone.utc,
    )

    assert date_only is False


def test_extracted_date_only_is_preserved():
    published_at, date_only = (
        _parse_extracted_date(
            "2026-02-27"
        )
    )

    assert published_at == datetime(
        2026,
        2,
        27,
        tzinfo=timezone.utc,
    )

    assert date_only is True


def test_extracted_precise_timestamp_is_preserved():
    published_at, date_only = (
        _parse_extracted_date(
            "2026-02-27T18:15:00+00:00"
        )
    )

    assert published_at == datetime(
        2026,
        2,
        27,
        18,
        15,
        tzinfo=timezone.utc,
    )

    assert date_only is False
