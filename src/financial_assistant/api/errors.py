from __future__ import annotations


class DeskError(Exception):
    """Base class for errors the API reports to the client."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DeskError):
    status_code = 404


class Conflict(DeskError):
    status_code = 409


class UpstreamUnavailable(DeskError):
    """A dependency (market data, LLM, search) did not answer."""

    status_code = 503
