"""Browser-backed :class:`Retriever` (CloakBrowser / Playwright).

This retriever reuses the existing
:class:`~pagemap.server.browser_session.BrowserSession` infrastructure.
It does not own a browser; the server is responsible for handing one
in via :attr:`FetchContext.session`.  When ``ctx.session`` is ``None``
or has no live Playwright ``Page``, :meth:`fetch` raises
:class:`RetrieverError` — the server should gate the call before
invoking the retriever (so the user gets a 503-style error rather than
a crash).

Adding a new browser-backed retriever (e.g. one with a different
patch level or remote control plane) is a matter of subclassing
:class:`Retriever` in another module and calling
:func:`register_retriever` with a factory.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import FetchContext, FetchedDocument, RetrieverError

logger = logging.getLogger(__name__)


class BrowserRetriever:
    """Fetch a URL using the live Playwright / CloakBrowser page.

    Attributes:
        name: ``"cloak"`` (canonical registry key).
        kind: ``"browser"`` (drives server-side gating).
    """

    name: str = "cloak"
    kind: str = "browser"

    def is_available(self) -> bool:
        """Always available — the server gates the real check.

        The server calls :func:`get_session` and yields a 503-style
        error before invoking the retcher if no browser is running,
        so the retriever itself can stay optimistic and let the
        server handle the negative case.
        """
        return True

    async def fetch(self, url: str, *, ctx: FetchContext) -> FetchedDocument:
        """Navigate to ``url`` and capture the resulting page state.

        The :class:`FetchedDocument` includes the live Playwright
        :class:`Page` in :attr:`browser_page` so the
        :class:`~pagemap.pipeline.extractor.Extractor` can run JS or
        read the accessibility tree.

        Raises:
            RetrieverError: when ``ctx.session`` is missing or the
                Playwright page is unavailable.
        """
        if ctx.session is None:
            raise RetrieverError(
                "BrowserRetriever.fetch called without FetchContext.session. "
                "The server is responsible for acquiring the browser session."
            )

        page: Any | None = None
        try:
            page = ctx.session.page
        except Exception as exc:  # nosec B110
            raise RetrieverError(
                f"BrowserRetriever could not obtain a Playwright page from the "
                f"provided session: {exc}"
            ) from exc
        if page is None:
            raise RetrieverError(
                "BrowserRetriever could not obtain a Playwright page from the "
                "provided session. Ensure the server is started with a browser."
            )

        # Navigate using the session's hybrid wait strategy.  The session
        # also performs cookie/storage reset and Accept-Language setting.
        nav_result = await ctx.session.navigate(url)

        # Pull HTML, headers, and any cookies the navigation set.
        try:
            raw_html = await ctx.session.get_page_html()
            final_url = await ctx.session.get_page_url()
        except Exception as exc:
            raise RetrieverError(f"Browser fetch failed: {exc}") from exc

        # Surface the response status (when available) so the extractor
        # can include it in metadata.  ``page.url`` is the live URL.
        status: int | None = None
        content_type: str | None = None
        cookies: dict[str, str] = {}
        try:
            nav = nav_result
            status = getattr(nav, "http_status", None) if nav else None
        except Exception:  # nosec B110
            status = None
        try:
            cookies_list = await page.context.cookies(final_url or url)
            for c in cookies_list or []:
                name = c.get("name") if isinstance(c, dict) else getattr(c, "name", None)
                value = c.get("value") if isinstance(c, dict) else getattr(c, "value", None)
                if name and value is not None:
                    cookies[name] = value
        except Exception:  # nosec B110
            cookies = {}

        metadata: dict[str, Any] = {
            "retriever": "cloak",
            "final_url": final_url,
        }
        if nav_result is not None:
            try:
                metadata["wait_strategy"] = getattr(nav_result, "strategy", None)
                settle = getattr(nav_result, "settle_metrics", None)
                if isinstance(settle, dict):
                    metadata["settle_metrics"] = settle
            except Exception:  # nosec B110
                pass

        return FetchedDocument(
            raw_html=raw_html or "",
            final_url=final_url or url,
            status=status,
            content_type=content_type,
            cookies=cookies,
            headers={},
            metadata=metadata,
            browser_page=page,
        )
