"""Exceptions raised by :mod:`pagemap.pipeline.retriever.providers`."""

from __future__ import annotations

from pagemap.pipeline.retriever.errors import WebFetchError


class ProviderError(WebFetchError):
    """Raised when a search provider fails."""


__all__ = ["ProviderError"]
