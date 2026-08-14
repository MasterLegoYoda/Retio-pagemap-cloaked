"""Retrievers — pluggable transports that turn a URL into a :class:`FetchedDocument`.

The built-in retrievers are:

* :class:`BrowserRetriever` (``name="cloak"``, ``kind="browser"``) —
  uses the live Playwright / CloakBrowser page.
* :class:`HttpRetriever` (``name="fetch"``, ``kind="http"``) — uses
  the pluggable :class:`HttpBackend` registry
  (``:mod:`pagemap.pipeline.retriever.http` ``).

Both register themselves on import via
:mod:`pagemap.pipeline._builtins`.  See :func:`register_retriever` for
the extension point.
"""

from __future__ import annotations

from .base import FetchContext, FetchedDocument, Retriever, RetrieverError, RetrieverNotFound
from .browser import BrowserRetriever
from .errors import (
    InvalidSessionName,
    SessionNotFound,
    WebFetchError,
)
from .httpfetch import HttpRetriever
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
from .registry import (
    _reset_for_tests,
    get_retriever,
    list_retrievers,
    register_retriever,
    resolve_retriever,
)
from .sessions import (
    DEFAULT_SESSION_ID,
    NEW_SESSION_PREFIX,
    NEW_SESSION_SENTINEL,
    SESSION_NAME_PATTERN,
    HttpSessionState,
    HttpSessionState as _HttpSessionState,  # noqa: F401
    SessionManager,
    WebSession,
    resolve_session_arg,
)

__all__ = [
    "BatchWebFetchEntry",
    "BatchWebFetchResult",
    "BrowserRetriever",
    "DEFAULT_SESSION_ID",
    "FetchContext",
    "FetchedDocument",
    "FetchFormat",
    "FetchMode",
    "HttpRetriever",
    "HttpSessionState",
    "InvalidSessionName",
    "NEW_SESSION_PREFIX",
    "NEW_SESSION_SENTINEL",
    "Retriever",
    "RetrieverError",
    "RetrieverNotFound",
    "SESSION_NAME_PATTERN",
    "SearchProviderName",
    "SessionInfo",
    "SessionManager",
    "SessionNotFound",
    "WebFetchError",
    "WebFetchResult",
    "WebSearchOutput",
    "WebSearchResult",
    "WebSession",
    "get_retriever",
    "list_retrievers",
    "register_retriever",
    "resolve_retriever",
    "resolve_session_arg",
    "_reset_for_tests",
]
