"""Bridge between the web_fetch layer and PageMap's existing BrowserSession.

The new ``web_search`` / ``web_fetch`` tools want a CloakBrowser-backed
transport, but they also need to be optional — they should work even when
no browser is currently running. This module exposes two small helpers:

* :func:`attach_browser_to_session` — bind the active ``BrowserSession`` to
  a :class:`WebSession` so subsequent calls reuse the same context.
* :func:`acquire_browser_page` — return a Playwright page from a
  :class:`WebSession`, creating one if necessary.

Both are deliberately conservative: if no browser is available they
``return None`` and let the caller fall back to the stdlib transport.
"""

from __future__ import annotations

from typing import Any

from pagemap.web_fetch import WebSession

__all__ = [
    "acquire_browser_page",
    "attach_browser_to_session",
]


def attach_browser_to_session(session: WebSession, browser_session: Any) -> None:
    """Store a reference to the active PageMap ``BrowserSession`` on a
    :class:`WebSession` so future tool calls can reuse the browser context.

    Safe to call multiple times — only the latest reference is kept.
    """
    session.browser = browser_session


def acquire_browser_page(session: WebSession) -> Any:
    """Return a Playwright page owned by ``session``'s browser.

    Returns ``None`` when no browser is attached — the caller should fall
    back to its non-browser transport.
    """
    browser_session = session.browser
    if browser_session is None:
        return None
    try:
        page = browser_session.page
    except Exception:  # nosec B110
        return None
    return page
