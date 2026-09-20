from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class StoredTriage(BaseModel):
    key: str
    anomaly_id: str
    verdict: str
    why_now: str

    # news_id of the cited headline, if any.
    headline_news_id: str | None = None

    model: str
    created_at: datetime


class TriageRepository:
    """
    Triage verdicts, one JSON file per reading.

    A reading is identified by the anomaly AND the exact
    headlines it was given, so new news produces a new
    reading while an unchanged desk replays the stored one:
    the same click gives the same answer, with or without a
    GPU behind it.
    """

    def __init__(self, directory: Path):
        self._directory = directory
        self._lock = threading.Lock()

    def get(self, key: str) -> StoredTriage | None:
        path = self._directory / f"{key}.json"

        with self._lock:
            if not path.is_file():
                return None

            try:
                return StoredTriage.model_validate_json(path.read_text())
            except ValueError:
                return None

    def save(self, triage: StoredTriage) -> StoredTriage:
        with self._lock:
            self._directory.mkdir(parents=True, exist_ok=True)

            (self._directory / f"{triage.key}.json").write_text(
                triage.model_dump_json(indent=2) + "\n"
            )

        return triage
