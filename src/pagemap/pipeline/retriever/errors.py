"""Exceptions raised by :mod:`pagemap.pipeline.retriever`.

Includes both the new retriever-protocol errors
(:class:`RetrieverError`, :class:`RetrieverNotFound`) and the
session-layer errors that moved over from the old
``pagemap.web_fetch`` package.
"""

from __future__ import annotations

from .base import RetrieverError, RetrieverNotFound


class WebFetchError(Exception):
    """Base class for retriever-layer errors (preserved from web_fetch)."""


class InvalidSessionName(WebFetchError, ValueError):
    """Raised when a session name fails validation."""


class SessionNotFound(WebFetchError, KeyError):
    """Raised when a named session does not exist in the registry."""

    def __init__(self, session_id: str, known: list[str] | None = None) -> None:
        super().__init__(session_id)
        self.session_id = session_id
        self.known = known or []

    def __str__(self) -> str:
        if self.known:
            sample = ", ".join(self.known[:5])
            more = "" if len(self.known) <= 5 else f" (+{len(self.known) - 5} more)"
            return f"Session '{self.session_id}' not found. Known sessions: {sample}{more}."
        return f"Session '{self.session_id}' not found."


__all__ = [
    "InvalidSessionName",
    "RetrieverError",
    "RetrieverNotFound",
    "SessionNotFound",
    "WebFetchError",
]
