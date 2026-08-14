"""Stub for the Tavily search API.

To enable: POST to ``https://api.tavily.com/search`` with ``TAVILY_API_KEY``
and parse the ``results`` list.
"""

from __future__ import annotations

from .base import ProviderContext, SearchProvider
from .errors import ProviderError


class TavilyProvider(SearchProvider):
    name = "tavily"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        recency: str | None = None,
        domain_filter: list[str] | None = None,
        ctx: ProviderContext | None = None,
    ) -> list[dict[str, str]]:
        raise ProviderError(
            "Tavily search provider is not yet implemented. "
            "POST to https://api.tavily.com/search with TAVILY_API_KEY and register "
            "via pagemap.web_fetch.providers.registry.register_provider('tavily', ...)."
        )

    def healthcheck(self) -> bool:
        return False
