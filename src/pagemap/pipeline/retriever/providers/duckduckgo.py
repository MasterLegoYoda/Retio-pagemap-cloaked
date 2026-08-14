"""DuckDuckGo HTML-scrape provider (concrete implementation).

Uses the lite HTML endpoint at ``https://html.duckduckgo.com/html/`` which
returns plain server-rendered HTML (no JavaScript required) and is the
zero-config way to wire ``web_search`` into PageMap. Operates through the
provided :class:`ProviderContext` so the call site controls browser reuse.
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse

from bs4 import BeautifulSoup

from .base import ProviderContext, SearchProvider
from .errors import ProviderError

logger = logging.getLogger(__name__)

_ENDPOINT = "https://html.duckduckgo.com/html/"
_USER_AGENT_HINT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _fetch_via_http(query: str) -> str:
    """Fallback: GET the HTML endpoint with stdlib ``urllib`` (no extra deps).

    Used when no browser is available in the session. This is the simplest
    transport; the MCP/CLI layer will prefer a browser-rendered fetch when
    one is available.
    """
    import urllib.request

    body = urllib.parse.urlencode({"q": query}).encode("ascii")
    req = urllib.request.Request(
        _ENDPOINT,
        data=body,
        method="POST",
        headers={
            "User-Agent": _USER_AGENT_HINT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — public endpoint
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _parse_results(html_text: str, *, max_results: int) -> list[dict[str, str]]:
    """Parse DuckDuckGo HTML result list into ``{title, url, snippet}``."""
    soup = BeautifulSoup(html_text, "lxml")
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    # DuckDuckGo HTML result rows are <a class="result__a" href="..."> for the
    # title and <a class="result__snippet"> / <td class="result__snippet"> for
    # the snippet. Use a tolerant walk.
    for a in soup.find_all("a", attrs={"class": re.compile(r"^result__a$")}):
        href = (a.get("href") or "").strip()
        title = _clean(a.get_text(" ", strip=True))
        if not href or not title:
            continue

        # DuckDuckGo wraps outbound links in a redirector. Strip it.
        url = _strip_ddg_redirect(href)
        if not url or url in seen:
            continue
        seen.add(url)

        # Find the adjacent snippet (best effort).
        snippet = ""
        result_node = a.find_parent("div", class_=re.compile(r"result\b"))
        if result_node is None:
            # Lite markup: snippet is in a sibling <td>.
            row = a.find_parent("tr")
            if row is not None:
                snip_node = row.find(["td", "a"], class_=re.compile(r"result__snippet"))
                if snip_node is not None:
                    snippet = _clean(snip_node.get_text(" ", strip=True))
        else:
            snip_node = result_node.find(class_=re.compile(r"result__snippet"))
            if snip_node is not None:
                snippet = _clean(snip_node.get_text(" ", strip=True))

        out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= max_results:
            break

    return out


def _strip_ddg_redirect(href: str) -> str:
    """DuckDuckGo wraps clicks in ``//duckduckgo.com/l/?uddg=<encoded>``."""
    if "uddg=" in href:
        try:
            parsed = urllib.parse.urlparse(href if href.startswith("http") else f"https:{href}")
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("uddg", [None])[0]
            if target:
                return urllib.parse.unquote(target)
        except Exception:  # nosec B110
            pass
    if href.startswith("//"):
        return "https:" + href
    return href


_CLEAN_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _CLEAN_RE.sub(" ", text or "").strip()


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        recency: str | None = None,  # currently unused — DDG HTML ignores it
        domain_filter: list[str] | None = None,
        ctx: ProviderContext | None = None,
    ) -> list[dict[str, str]]:
        if not query or not query.strip():
            raise ProviderError("Query must be a non-empty string.")

        if ctx is not None and getattr(ctx, "min_delay_ms", 0) > 0:
            await asyncio.sleep(ctx.min_delay_ms / 1000.0)

        # Transport: prefer the session's browser if one is available. The
        # MCP/CLI layer attaches the Playwright page; the stdlib fallback
        # keeps the provider usable in tests and minimal installs.
        html_text: str
        browser_page = ctx.history[-1].get("page") if ctx and ctx.history else None
        if browser_page is not None:
            try:
                # type: ignore[attr-defined]
                response = await browser_page.goto(_ENDPOINT, wait_until="domcontentloaded")
                if response is not None:
                    await browser_page.fill("input[name='q']", query)
                    await browser_page.press("input[name='q']", "Enter")
                    await browser_page.wait_for_load_state("domcontentloaded")
                html_text = await browser_page.content()
            except Exception as exc:
                logger.warning("DDG browser path failed (%s); falling back to stdlib", exc)
                html_text = await asyncio.to_thread(_fetch_via_http, query)
        else:
            html_text = await asyncio.to_thread(_fetch_via_http, query)

        results = _parse_results(html_text, max_results=max_results)

        # Apply domain_filter post-hoc (no native support in DDG HTML).
        if domain_filter:
            allow = [d.lower() for d in domain_filter if not d.startswith("-")]
            deny = [d[1:].lower() for d in domain_filter if d.startswith("-")]
            if allow:
                results = [
                    r for r in results if any(d in r["url"].lower() for d in allow)
                ]
            if deny:
                results = [
                    r for r in results
                    if not any(d in r["url"].lower() for d in deny)
                ]

        return results

    def healthcheck(self) -> bool:
        return True
