"""Auto-register all built-in search providers on import.

This module is imported by :mod:`pagemap.web_fetch` so that the registry
contains every provider that ships in the box. Adding a new provider
means: drop a module under :mod:`pagemap.web_fetch.providers`, then add
one line below.
"""

from __future__ import annotations

# Stubs — registered so they appear in `available_providers()` and
# surface a clear "not yet implemented" error when selected.
from .bing import BingProvider
from .brave import BraveProvider

# Concrete implementations
from .duckduckgo import DuckDuckGoProvider
from .exa import ExaProvider
from .firecrawl import FirecrawlProvider
from .google import GoogleProvider
from .registry import register_provider
from .searxng import SearXNGProvider
from .tavily import TavilyProvider


def _register_builtins() -> None:
    register_provider("duckduckgo", lambda: DuckDuckGoProvider())
    register_provider("brave", lambda: BraveProvider())
    register_provider("bing", lambda: BingProvider())
    register_provider("google", lambda: GoogleProvider())
    register_provider("searxng", lambda: SearXNGProvider())
    register_provider("exa", lambda: ExaProvider())
    register_provider("tavily", lambda: TavilyProvider())
    register_provider("firecrawl", lambda: FirecrawlProvider())


_register_builtins()
