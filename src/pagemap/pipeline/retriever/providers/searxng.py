"""Stub for a SearXNG meta-search provider.

To enable: GET ``${SEARXNG_URL}/search?q=...&format=json`` (JSON must be
enabled in ``settings.yml``) and map the ``results`` list.
"""

from __future__ import annotations

from .base import ProviderContext, SearchProvider
from .errors import ProviderError


class SearXNGProvider(SearchProvider):
    name = "searxng"

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
            "SearXNG search provider is not yet implemented. "
            "Add an HTTP call to ${SEARXNG_URL}/search?format=json&q=... and register "
            "via pagemap.web_fetch.providers.registry.register_provider('searxng', ...)."
        )

    def healthcheck(self) -> bool:
        return False
