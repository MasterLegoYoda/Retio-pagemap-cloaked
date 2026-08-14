"""HTTP-only :class:`Retriever` (curl_cffi / httpx / urllib).

This retriever reuses the existing
:mod:`pagemap.pipeline.retriever.http` registry so that ``--fast-backend``,
``PAGEMAP_FAST_BACKEND`` and the
``pip install 'retio-pagemap[fast]'`` extra keep working.  No new
configuration knobs are introduced — the same resolution rules
(``curl_cffi`` → ``httpx`` → ``urllib``) apply.

Adding a new HTTP-only retriever is just a matter of subclassing
:class:`Retriever` and calling :func:`register_retriever`.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import FetchContext, FetchedDocument, RetrieverError
from .http.base import HttpResponse
from .http.registry import get_backend, list_backends, resolve_backend
from .sessions import HttpSessionState  # noqa: TID252 — same package

logger = logging.getLogger(__name__)


def _parse_set_cookie(value: str) -> tuple[str, str] | None:
    """Parse the ``name=value`` pair out of a ``Set-Cookie`` header.

    Returns ``None`` when the header is malformed or carries only
    attributes (e.g. ``"expires=…"`` with no name=value).
    """
    if not value:
        return None
    first = value.split(";", 1)[0].strip()
    if "=" not in first:
        return None
    name, _, val = first.partition("=")
    name = name.strip()
    val = val.strip()
    if not name:
        return None
    return name, val


class HttpRetriever:
    """HTTP-only retriever backed by an :class:`HttpBackend`.

    Attributes:
        name: ``"fetch"`` (canonical registry key).
        kind: ``"http"`` (drives server-side gating).
    """

    name: str = "fetch"
    kind: str = "http"

    def __init__(self, *, prefer: str | None = None) -> None:
        self._prefer: str | None = prefer or "auto"
        self._backend = None  # lazy

    def is_available(self) -> bool:
        """Return ``True`` iff at least one HTTP backend is installed.

        The ``urllib`` backend is always available, so this returns
        ``True`` even in a fresh venv with no optional dependencies.
        """
        try:
            self._get_backend()
            return True
        except Exception:  # nosec B110 — defensive
            return False

    def _get_backend(self) -> Any:
        if self._backend is None:
            if self._prefer and self._prefer != "auto":
                self._backend = get_backend(self._prefer)
            else:
                self._backend = resolve_backend("auto")
        return self._backend

    async def fetch(self, url: str, *, ctx: FetchContext) -> FetchedDocument:
        """Fetch ``url`` and return a :class:`FetchedDocument`.

        Cookies are merged into the session's :class:`HttpSessionState`
        (when one is attached) so successive calls in the same
        session look continuous to bot detection.

        Raises:
            RetrieverError: when no HTTP backend is available or the
                transport fails.
        """
        try:
            backend = self._get_backend()
        except Exception as exc:
            raise RetrieverError(
                f"HTTP backend not available: {exc}. "
                f"Install 'retio-pagemap[fast]' for curl_cffi / httpx."
            ) from exc

        # Cookie merge: incoming ctx.cookies (per-call override) wins
        # over the session jar, which in turn wins over the backend's
        # own defaults.  We send the union as a Cookie header.
        cookies: dict[str, str] = {}
        if isinstance(ctx.session, object) and getattr(ctx.session, "http", None) is not None:
            cookies.update(getattr(ctx.session.http, "cookies", {}) or {})
        if ctx.cookies:
            cookies.update(ctx.cookies)

        headers: dict[str, str] = dict(ctx.headers or {})
        # If the call carries a session, give the backend the session's UA.
        if isinstance(ctx.session, object) and getattr(ctx.session, "http", None) is not None:
            ua = getattr(ctx.session.http, "user_agent", None)
            if ua and "user-agent" not in {k.lower() for k in headers}:
                headers["User-Agent"] = ua

        try:
            response: HttpResponse = await backend.fetch(
                url,
                headers=headers or None,
                cookies=cookies or None,
                timeout=ctx.timeout,
                follow_redirects=ctx.follow_redirects,
                impersonate=ctx.impersonate,
            )
        except Exception as exc:
            raise RetrieverError(f"HTTP fetch failed: {exc}") from exc

        # Pull Set-Cookie values off the response for the session jar.
        set_cookies: dict[str, str] = {}
        # `HttpBackend` parses the `set_cookies` list — use it when present.
        for sc in getattr(response, "set_cookies", []) or []:
            name = getattr(sc, "name", None)
            value = getattr(sc, "value", None)
            if name and value is not None:
                set_cookies[name] = value
        # Fall back to raw headers if the backend didn't parse them.
        if not set_cookies:
            raw_headers = response.headers or {}
            for key in ("set-cookie", "Set-Cookie"):
                if key in raw_headers:
                    for piece in str(raw_headers[key]).split("\n"):
                        parsed = _parse_set_cookie(piece)
                        if parsed:
                            set_cookies[parsed[0]] = parsed[1]

        # Persist cookies on the session's HttpSessionState when present.
        if isinstance(ctx.session, object) and getattr(ctx.session, "http", None) is not None:
            try:
                http_state: HttpSessionState = ctx.session.http
                http_state.cookies.update(set_cookies)
                http_state.request_count += 1
            except Exception:  # nosec B110
                pass

        metadata: dict[str, Any] = {
            "retriever": "fetch",
            "backend": getattr(backend, "name", "unknown"),
            "final_url": response.url or url,
        }
        if set_cookies:
            metadata["set_cookies"] = set_cookies

        # Build the cookies map carried on the FetchedDocument itself.
        cookies_out: dict[str, str] = {}
        for sc in getattr(response, "set_cookies", []) or []:
            name = getattr(sc, "name", None)
            value = getattr(sc, "value", None)
            if name and value is not None:
                cookies_out[name] = value
        if not cookies_out and set_cookies:
            cookies_out.update(set_cookies)

        # Pull Content-Type if present.
        content_type: str | None = response.headers.get("content-type") or response.headers.get("Content-Type")

        return FetchedDocument(
            raw_html=response.text or "",
            final_url=response.url or url,
            status=response.status,
            content_type=content_type,
            cookies=cookies_out,
            headers=dict(response.headers or {}),
            metadata=metadata,
            browser_page=None,
        )


__all__ = ["HttpRetriever", "list_backends"]
