from __future__ import annotations

from datetime import datetime

from financial_assistant.domain import SourceDocument


def is_published_by(
    document: SourceDocument,
    cutoff: datetime,
) -> bool:
    """
    Point-in-time admissibility of a document.

    A document may only explain an anomaly if it is
    KNOWN to have been public at the cutoff:

      - undated documents are never admissible;
      - a date-only document must be dated strictly
        before the cutoff day, because its time of day
        is unknown;
      - a timestamped document must be at or before
        the cutoff instant.
    """

    if document.published_at is None:
        return False

    if document.published_date_only:
        return document.published_at.date() < cutoff.date()

    return document.published_at <= cutoff
