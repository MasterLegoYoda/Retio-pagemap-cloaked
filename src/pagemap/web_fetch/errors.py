"""Errors raised by the web fetch / search layer."""

from __future__ import annotations


class WebFetchError(Exception):
    """Base class for web fetch / search errors."""


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


class ProviderError(WebFetchError):
    """Raised when a search or fetch provider fails."""


class ExtractionError(WebFetchError):
    """Raised when content extraction from an HTML payload fails."""
