from __future__ import annotations

import threading
from pathlib import Path

from financial_assistant.api.models import Investigation


class InvestigationRepository:
    """
    Investigations, one replayable JSON file per run.

    Runs are kept in memory while the process lives and
    reloaded from disk after a restart, so a finished
    investigation survives a demo-day crash.
    """

    def __init__(self, directory: Path):
        self._directory = directory
        self._lock = threading.Lock()
        self._runs: dict[str, Investigation] = {}
        self._loaded = False

    def save(self, investigation: Investigation) -> Investigation:
        # Workers keep mutating their run while readers
        # serialise it, so the store keeps its own copy.
        snapshot = investigation.model_copy(deep=True)

        with self._lock:
            self._runs[snapshot.investigation_id] = snapshot

            self._directory.mkdir(parents=True, exist_ok=True)
            self._path(snapshot.investigation_id).write_text(
                snapshot.model_dump_json(indent=2) + "\n"
            )

        return investigation

    def get(self, investigation_id: str) -> Investigation | None:
        with self._lock:
            self._load_all()
            return self._runs.get(investigation_id)

    def list(self) -> tuple[Investigation, ...]:
        with self._lock:
            self._load_all()

            return tuple(
                sorted(
                    self._runs.values(),
                    key=lambda run: run.created_at,
                    reverse=True,
                )
            )

    def _path(self, investigation_id: str) -> Path:
        return self._directory / f"{investigation_id}.json"

    def _load_all(self) -> None:
        if self._loaded:
            return

        self._loaded = True

        if not self._directory.is_dir():
            return

        for path in self._directory.glob("*.json"):
            try:
                run = Investigation.model_validate_json(path.read_text())
            except ValueError:
                continue

            self._runs.setdefault(run.investigation_id, run)
