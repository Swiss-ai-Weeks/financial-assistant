from __future__ import annotations

import threading
from pathlib import Path

from financial_assistant.api.models import Portfolio


class PortfolioRepository:
    """
    The manager's book, persisted as one JSON file.

    On first start the book is copied from the seed file
    so the demo opens on a populated desk.
    """

    def __init__(self, path: Path, *, seed_file: Path | None = None):
        self._path = path
        self._seed_file = seed_file
        self._lock = threading.Lock()

    def load(self) -> Portfolio:
        with self._lock:
            if self._path.is_file():
                return Portfolio.model_validate_json(self._path.read_text())

            if self._seed_file is not None and self._seed_file.is_file():
                return Portfolio.model_validate_json(
                    self._seed_file.read_text()
                )

            return Portfolio()

    def save(self, portfolio: Portfolio) -> Portfolio:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(portfolio.model_dump_json(indent=2) + "\n")

        return portfolio

    def reset(self) -> Portfolio:
        with self._lock:
            self._path.unlink(missing_ok=True)

        return self.load()
