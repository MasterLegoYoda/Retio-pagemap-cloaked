"""Stub for a Google search HTML-scrape provider.

Google does not publish a free web-search API for this kind of use. The
realistic implementation scrapes the public ``https://www.google.com/search``
results page (no API key) and parses organic hits. That's brittle and may
violate Google's ToS — only enable behind a feature flag.
"""

from __future__ import annotations

from ..errors import ProviderError
from .base import ProviderContext, SearchProvider


class GoogleProvider(SearchProvider):
    name = "google"

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
            "Google search provider is not yet implemented. "
            "Scrape https://www.google.com/search?q=... via the session browser "
            "and parse the result list. Wire it in via "
            "pagemap.web_fetch.providers.registry.register_provider('google', ...)."
        )

    def healthcheck(self) -> bool:
        return False
