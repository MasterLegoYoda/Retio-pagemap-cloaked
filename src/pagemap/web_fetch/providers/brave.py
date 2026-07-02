"""Stub for the Brave search provider.

To enable: implement :class:`SearchProvider.search` using the Brave Web
Search API (``https://api.search.brave.com/res/v1/web/search``) and the
``BRAVE_API_KEY`` environment variable. Keep the class import-safe so that
simply registering it in :mod:`registry` is enough to wire it in.
"""

from __future__ import annotations

from ..errors import ProviderError
from .base import ProviderContext, SearchProvider


class BraveProvider(SearchProvider):
    name = "brave"

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
            "Brave search provider is not yet implemented. "
            "Add an API call to https://api.search.brave.com/res/v1/web/search "
            "using BRAVE_API_KEY and register an instance via "
            "pagemap.web_fetch.providers.registry.register_provider('brave', ...)."
        )

    def healthcheck(self) -> bool:
        return False
