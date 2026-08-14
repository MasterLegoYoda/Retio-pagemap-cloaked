# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Protocol and shared types for HTTP backends.

Every backend in :mod:`pagemap.web_fetch.http.backends` implements the
:class:`HttpBackend` protocol.  The protocol deliberately stays small:
just enough to fetch a single URL with a small set of knobs.  Cookie
state and connection pooling are *not* part of the protocol — the
caller (``pagemap.web_fetch.http_session``) tracks cookies per
:class:`pagemap.web_fetch.sessions.WebSession` and feeds them in on
each call.

Adding a new backend is two steps:

1.  Subclass or duck-type ``HttpBackend`` in a module under
    :mod:`pagemap.web_fetch.http.backends`.
2.  Call :func:`pagemap.web_fetch.http.registry.register_backend`
    with a factory (typically ``lambda: MyBackend()``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SetCookie:
    """A parsed ``Set-Cookie`` header value.

    ``name`` and ``value`` are always populated.  The remaining
    attributes (``expires``, ``max_age``, ``domain``, ``path``,
    ``secure``, ``http_only``, ``same_site``) default to ``None`` and
    are filled in when present in the header.  They are advisory —
    :class:`pagemap.web_fetch.sessions.HttpSessionState` does a simple
    ``name -> value`` merge, ignoring path/domain scoping.
    """

    name: str
    value: str
    expires: int | None = None
    max_age: int | None = None
    domain: str | None = None
    path: str | None = None
    secure: bool = False
    http_only: bool = False
    same_site: str | None = None


@dataclass
class HttpResponse:
    """Uniform response object returned by every backend.

    ``text`` is always populated (the body decoded as text using the
    response charset, or ``utf-8`` as a last resort).  ``headers`` is a
    flat ``str -> str`` mapping.  ``set_cookies`` is the list of
    :class:`SetCookie` values parsed out of the response headers, in
    the order they appeared.
    """

    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""
    set_cookies: list[SetCookie] = field(default_factory=list)


@runtime_checkable
class HttpBackend(Protocol):
    """Pluggable HTTP transport for ``web_fetch`` fast mode.

    Implementations should be cheap to construct and stateless across
    calls.  Per-session state (cookies, default headers) is passed in
    by the caller so backends can stay free of hidden state.
    """

    #: Canonical backend name (matches the registry key).
    name: str

    def is_available(self) -> bool:
        """Return ``True`` if the backend's optional dependency is importable.

        Implementations should perform the check synchronously and
        cheaply (typically: ``importlib.util.find_spec(...)``).
        """
        ...

    async def fetch(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        max_redirects: int = 5,
        impersonate: str | None = None,
    ) -> HttpResponse:
        """Fetch ``url`` and return an :class:`HttpResponse`.

        Args:
            url: Absolute http/https URL to fetch.
            headers: Extra request headers.  The backend is responsible
                for adding a sensible default User-Agent and
                Accept-Language when ``headers`` does not contain one.
            cookies: ``name -> value`` mapping.  Backends send them
                as a ``Cookie`` header.
            timeout: Per-request timeout in seconds.
            follow_redirects: When ``False``, raise on any 3xx response
                that would normally be followed.
            max_redirects: Hard cap on the number of redirects to
                follow.  Backends should treat this as a safety bound
                and never loop indefinitely.
            impersonate: Backend-specific impersonation hint
                (e.g. ``"chrome"`` for ``curl_cffi``).  Backends
                without TLS impersonation may ignore this.

        Raises:
            HttpBackendError: on transport / protocol failures.
        """
        ...

    async def aclose(self) -> None:
        """Release any held resources (connection pools, sessions).

        Default is a no-op so stateless backends don't have to
        override it.
        """
        ...


class HttpBackendError(Exception):
    """Raised by an :class:`HttpBackend` for transport-level failures.

    The original exception is available via ``__cause__``; ``str(exc)``
    is the human-readable summary surfaced to MCP clients.
    """
