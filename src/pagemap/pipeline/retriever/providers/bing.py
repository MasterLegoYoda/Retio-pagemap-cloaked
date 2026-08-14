"""Stub for the Bing Web Search provider.

To enable: call ``https://api.bing.microsoft.com/v7.0/search?q=...`` with a
``Ocp-Apim-Subscription-Key`` header (``BING_API_KEY``) and parse the
``webPages.value`` list.
"""

from __future__ import annotations

from .base import ProviderContext, SearchProvider
from .errors import ProviderError


class BingProvider(SearchProvider):
    name = "bing"

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
            "Bing search provider is not yet implemented. "
            "Add an API call to https://api.bing.microsoft.com/v7.0/search "
            "using BING_API_KEY and register an instance via "
            "pagemap.web_fetch.providers.registry.register_provider('bing', ...)."
        )

    def healthcheck(self) -> bool:
        return False
