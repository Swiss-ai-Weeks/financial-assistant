"""
Whether a story is actually about a company.

News feeds tag a story to every ticker it mentions in
passing, and keyword search matches a bank every time one
of its analysts is quoted. Both the news sources and the
news service need the same notion of "about".
"""

from __future__ import annotations

import re

from financial_assistant.api.models import NewsItem


LEGAL_WORDS = {
    "the", "inc", "inc.", "corp", "corp.", "corporation", "company",
    "co", "co.", "companies", "group", "holdings", "plc", "ltd", "&",
}

# Leading words too common to identify a company alone.
GENERIC_WORDS = {
    "american", "bank", "first", "general", "home", "international",
    "national", "united",
}


# A two-word alias ending in one of these is a fragment:
# "Bank of" would match Bank of Montreal.
CONNECTING_WORDS = {"of", "and", "the", "&", "de", "for"}


def company_phrase(ticker: str, company: str) -> str:
    """
    The name a journalist would write: the registered name
    without its legal form. Falls back to the ticker.
    """

    words = [
        word.strip(",")
        for word in company.split()
        if word.strip(",").lower() not in LEGAL_WORDS
    ]

    return " ".join(words) if words and company != ticker else ticker


def company_aliases(ticker: str, company: str) -> tuple[str, ...]:
    """
    Strings whose presence shows a story is about the
    company: "Bank of America Corporation" is written
    "Bank of America", "NVIDIA Corporation" is "NVIDIA".
    """

    words = [
        word.strip(",")
        for word in company.split()
        if word.strip(",").lower() not in LEGAL_WORDS
    ]

    aliases = {ticker}

    if words and company != ticker:
        aliases.add(" ".join(words))

        if len(words) >= 2 and words[1].lower() not in CONNECTING_WORDS:
            aliases.add(" ".join(words[:2]))

        if len(words[0]) >= 5 and words[0].lower() not in GENERIC_WORDS:
            aliases.add(words[0])

    return tuple(sorted(aliases, key=len, reverse=True))


def relevance(item: NewsItem, aliases: tuple[str, ...]) -> int:
    """
    2 when the headline names the company, 1 when only
    the summary does, 0 when the feed merely tagged it.
    """

    def mentions(text: str) -> bool:
        return any(
            re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text)
            for alias in aliases
        )

    if mentions(item.title):
        return 2

    return 1 if mentions(item.summary) else 0


def one_per_story(items) -> list[NewsItem]:
    """
    Collapse the same story arriving from several providers.

    Providers disagree on the URL (one links the publisher,
    another its own redirect), so URLs cannot identify a
    story. Its headline and publication day can. Without
    this, one article read through two feeds would count as
    two pieces of evidence.

    The copy kept is the one that links the publisher
    directly, then the one with the fuller summary.
    """

    def quality(item: NewsItem) -> tuple[bool, int]:
        return ("finnhub.io" not in item.url, len(item.summary))

    best: dict[tuple[str, str], NewsItem] = {}

    for item in items:
        key = (
            re.sub(r"[^a-z0-9]+", "", item.title.lower()),
            item.published_at.date().isoformat(),
        )

        if key not in best or quality(item) > quality(best[key]):
            best[key] = item

    return list(best.values())
