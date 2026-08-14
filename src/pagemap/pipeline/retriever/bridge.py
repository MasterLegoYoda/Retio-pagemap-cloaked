"""Bridge between the page-map browser session and a pipeline :class:`WebSession`.

The :class:`BrowserRetriever` reads ``ctx.session.page`` to get the
Playwright :class:`Page` to drive.  The :class:`WebSession` lives in
:mod:`pagemap.pipeline.retriever.sessions` and is shared with the
``web_fetch`` tool.  This module is the glue: it attaches the live
``BrowserSession`` to a :class:`WebSession` and helps the retriever
extract the :class:`Page` from it.

The functions are deliberately defensive: if no browser is running
they return ``None`` and let the caller fall back to its non-browser
transport.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "acquire_browser_page",
    "attach_browser_to_session",
]


def attach_browser_to_session(session: Any, browser_session: Any) -> None:
    """Bind the active PageMap ``BrowserSession`` to a
    :class:`WebSession` so future calls reuse the browser context.

    Safe to call multiple times — only the latest reference is kept.
    """
    session.browser = browser_session


def acquire_browser_page(session: Any) -> Any:
    """Return a Playwright :class:`Page` owned by ``session``'s browser.

    Returns ``None`` when no browser is attached — the caller should
    fall back to its non-browser transport.
    """
    browser_session = getattr(session, "browser", None)
    if browser_session is None:
        return None
    try:
        page = browser_session.page
    except Exception:  # nosec B110
        return None
    return page
