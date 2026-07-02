"""Web fetch and search layer for PageMap.

Provides agent-facing tools for plain web access (``web_search``,
``web_fetch``, ``batch_web_fetch``) alongside PageMap's existing browser
automation. Backed by a pluggable provider registry so additional search
backends (Brave, Bing, Google scrape, SearXNG, Exa, Tavily, Firecrawl) and
fetch backends (``fast`` mode) can be added without changing tool code.

Sessions are first-class: tools accept an optional ``session`` argument
that resolves to either a long-lived default session, a freshly created
session (``"new"`` or ``"new:<name>"``), or a previously created session id.
"""

from __future__ import annotations

from . import providers as _providers  # noqa: F401  (registers built-in providers)
from .errors import (
    ExtractionError,
    InvalidSessionName,
    ProviderError,
    SessionNotFound,
    WebFetchError,
)
from .models import (
    BatchWebFetchEntry,
    BatchWebFetchResult,
    FetchFormat,
    FetchMode,
    SearchProviderName,
    SessionInfo,
    WebFetchResult,
    WebSearchOutput,
    WebSearchResult,
)
from .providers import (  # noqa: F401
    PROVIDERS,
    available_providers,
    get_provider,
    list_provider_names,
    register_provider,
)
from .sessions import (
    DEFAULT_SESSION_ID,
    NEW_SESSION_PREFIX,
    NEW_SESSION_SENTINEL,
    SESSION_NAME_PATTERN,
    SessionManager,
    WebSession,
    resolve_session_arg,
)

__all__ = [
    "DEFAULT_SESSION_ID",
    "NEW_SESSION_PREFIX",
    "NEW_SESSION_SENTINEL",
    "PROVIDERS",
    "SESSION_NAME_PATTERN",
    "BatchWebFetchEntry",
    "BatchWebFetchResult",
    "ExtractionError",
    "FetchFormat",
    "FetchMode",
    "InvalidSessionName",
    "ProviderError",
    "SearchProviderName",
    "SessionInfo",
    "SessionManager",
    "SessionNotFound",
    "WebFetchError",
    "WebFetchResult",
    "WebSearchOutput",
    "WebSearchResult",
    "WebSession",
    "available_providers",
    "get_provider",
    "list_provider_names",
    "register_provider",
    "resolve_session_arg",
]
