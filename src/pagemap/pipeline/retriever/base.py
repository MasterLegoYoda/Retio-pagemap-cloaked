"""Protocols and value objects for :mod:`pagemap.pipeline.retriever`.

Two protocols (and their result dataclasses) sit at the heart of the
package:

* :class:`Retriever` — turns a URL into a :class:`FetchedDocument` (raw
  HTML plus transport metadata such as status, headers, and an
  optional :class:`playwright.async_api.Page`).

A :class:`~pagemap.pipeline.core.Pipeline` glues a :class:`Retriever` to
an :class:`~pagemap.pipeline.extractor.Extractor` and exposes a single
:meth:`~pagemap.pipeline.core.Pipeline.run` entry point.

Adding a new retriever is a two-step process:

1.  Subclass or duck-type :class:`Retriever` in a module under
    :mod:`pagemap.pipeline.retriever`.
2.  Call :func:`pagemap.pipeline.retriever.register_retriever` with a
    factory (typically ``lambda: MyRetriever()``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class FetchContext:
    """Per-call context handed to a :class:`Retriever`.

    Attributes:
        session: A long-lived :class:`WebSession` (or ``None`` for
            stateless calls). The retriever reads/writes cookies on it
            and records activity.
        cookies: ``name -> value`` mapping. The retriever sends them as
            a ``Cookie`` header (HTTP) or as Playwright
            ``context.add_cookies`` (browser).
        headers: Extra request headers.
        timeout: Per-request timeout in seconds.
        follow_redirects: When ``False``, raise on any 3xx response that
            would normally be followed.
        impersonate: Backend-specific impersonation hint
            (e.g. ``"chrome"`` for ``curl_cffi``).  HTTP fetchers
            without TLS impersonation may ignore this.
        request_id: A unique id for the call, used in logs and
            telemetry.
        extras: Implementation-specific extras (e.g. proxy config,
            GeoIP, humanize, persistent profile).
    """

    session: Any | None = None
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    follow_redirects: bool = True
    impersonate: str | None = None
    request_id: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchedDocument:
    """Result of a single :class:`Retriever` invocation.

    Attributes:
        raw_html: The page HTML as a string.  For the browser retriever
            this is ``page.content()``; for HTTP fetchers it is the
            response body decoded as text.
        final_url: The URL after redirects.
        status: HTTP status code (when known).
        content_type: ``Content-Type`` header value (when known).
        cookies: ``name -> value`` cookies received from the server in
            this call (not the full session jar).
        headers: Flat ``str -> str`` mapping of response headers.
        metadata: Retriever-specific metadata (e.g. backend name,
            timing, redirect chain).
        browser_page: The live Playwright :class:`Page` object when the
            retriever is browser-backed.  ``None`` for HTTP-only
            fetchers.  Hand this to the
            :class:`~pagemap.pipeline.extractor.Extractor` if it needs
            to run JS or read the accessibility tree.
    """

    raw_html: str
    final_url: str = ""
    status: int | None = None
    content_type: str | None = None
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    browser_page: Any | None = None


@runtime_checkable
class Retriever(Protocol):
    """Pluggable transport that turns a URL into a :class:`FetchedDocument`.

    Implementations should be cheap to construct.  Per-session state
    (cookies, default headers) is passed in via
    :class:`FetchContext` so retrievers can stay free of hidden state.
    """

    #: Canonical retriever name (matches the registry key).
    name: str

    #: Transport family.  Drives routing and capability checks in the
    #: server (``execute_action`` requires ``"browser"``; ``web_fetch
    #: mode="fast"`` forces ``"http"``).
    kind: Literal["browser", "http", "other"]

    def is_available(self) -> bool:
        """Return ``True`` if this retriever can be used right now.

        For browser retrievers this typically means: a browser session
        is running.  For HTTP retrievers: at least one optional
        dependency (``curl_cffi`` / ``httpx`` / ``urllib``) is
        importable.
        """
        ...

    async def fetch(self, url: str, *, ctx: FetchContext) -> FetchedDocument:
        """Fetch ``url`` and return a :class:`FetchedDocument`.

        Raises:
            RetrieverError: on transport / protocol failures.
        """
        ...


class RetrieverError(Exception):
    """Raised by a :class:`Retriever` for transport-level failures.

    The original exception is available via ``__cause__``; ``str(exc)``
    is the human-readable summary surfaced to MCP clients.
    """


class RetrieverNotFound(KeyError):
    """No retriever is registered under the requested name.

    Subclasses :class:`KeyError` so ``except KeyError`` keeps working,
    but is its own class so callers can catch it specifically.
    """

    def __init__(self, name: str, *, available: list[str] | None = None) -> None:
        self.name = name
        self.available = available or []
        super().__init__(name)

    def __str__(self) -> str:  # pragma: no cover — formatting
        if self.available:
            return f"Retriever '{self.name}' is not registered. Available: {', '.join(self.available)}."
        return f"Retriever '{self.name}' is not registered."
