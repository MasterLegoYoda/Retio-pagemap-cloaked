"""Base classes for search providers."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderContext:
    """Per-call context handed to a provider.

    The transport (``browser`` vs raw HTTP) and request shaping are decided
    by the MCP/CLI layer. Providers use this context to issue the actual
    request and to record session activity.
    """

    session_id: str
    history: list[dict[str, Any]]
    min_delay_ms: int = 0


class SearchProvider(abc.ABC):
    """Abstract interface for a search provider."""

    #: Canonical provider name. Must match the key in ``PROVIDERS``.
    name: str

    @abc.abstractmethod
    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        recency: str | None = None,
        domain_filter: list[str] | None = None,
        ctx: ProviderContext | None = None,
    ) -> list[dict[str, str]]:
        """Execute a search and return ``[{"title", "url", "snippet"}]``.

        Providers may raise :class:`pagemap.web_fetch.errors.ProviderError`
        for non-recoverable failures.
        """
        raise NotImplementedError

    def healthcheck(self) -> bool:
        """Optional liveness check. Default: ``True``."""
        return True
