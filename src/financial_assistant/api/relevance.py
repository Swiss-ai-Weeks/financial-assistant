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
