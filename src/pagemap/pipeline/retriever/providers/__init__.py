"""Search provider implementations (pluggable).

Each provider lives in its own module and exposes a single ``Provider``
class implementing :class:`pagemap.web_fetch.providers.base.SearchProvider`.
Concrete providers are registered in :mod:`pagemap.web_fetch.providers.registry`
under their canonical name (e.g. ``"duckduckgo"``).
"""

from __future__ import annotations

from . import _builtins as _builtins  # noqa: F401  (registers built-in providers)
from .base import SearchProvider
from .registry import (
    PROVIDERS,
    available_providers,
    get_provider,
    list_provider_names,
    register_provider,
)

__all__ = [
    "PROVIDERS",
    "SearchProvider",
    "available_providers",
    "get_provider",
    "list_provider_names",
    "register_provider",
]
