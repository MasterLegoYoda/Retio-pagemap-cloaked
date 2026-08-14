"""Stub for the Firecrawl search/scrape provider.

To enable: call ``https://api.firecrawl.dev/v1/search`` with
``FIRECRAWL_API_KEY`` and parse the ``data`` list.
"""

from __future__ import annotations

from .base import ProviderContext, SearchProvider
from .errors import ProviderError


class FirecrawlProvider(SearchProvider):
    name = "firecrawl"

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
            "Firecrawl search provider is not yet implemented. "
            "POST to https://api.firecrawl.dev/v1/search with FIRECRAWL_API_KEY "
            "and register via "
            "pagemap.web_fetch.providers.registry.register_provider('firecrawl', ...)."
        )

    def healthcheck(self) -> bool:
        return False
