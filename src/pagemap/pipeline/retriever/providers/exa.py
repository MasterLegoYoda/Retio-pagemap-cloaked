"""Stub for the Exa neural-search provider.

To enable: call ``https://api.exa.ai/search`` with ``EXA_API_KEY`` and
parse the ``results`` list.
"""

from __future__ import annotations

from .base import ProviderContext, SearchProvider
from .errors import ProviderError


class ExaProvider(SearchProvider):
    name = "exa"

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
            "Exa search provider is not yet implemented. "
            "POST to https://api.exa.ai/search with EXA_API_KEY and register "
            "via pagemap.web_fetch.providers.registry.register_provider('exa', ...)."
        )

    def healthcheck(self) -> bool:
        return False
