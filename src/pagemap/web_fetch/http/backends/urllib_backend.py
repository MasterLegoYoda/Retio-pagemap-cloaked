# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""``urllib``-backed :class:`HttpBackend` (stdlib fallback).

This is the always-available transport: no extra dependencies, no
TLS impersonation, no connection pooling.  It exists so that
``mode="fast"`` keeps working on minimal installs (the only Python
dependency is the standard library) and on platforms where neither
``curl_cffi`` nor ``httpx`` wheel is available.

Synchronous I/O is offloaded to a worker thread via
``asyncio.to_thread`` so the rest of the async stack stays
non-blocking.
"""

from __future__ import annotations

import asyncio
import contextlib
import http.cookiejar
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping

from ..base import HttpBackendError, HttpResponse, SetCookie

logger = logging.getLogger(__name__)

#: ``urllib`` cannot impersonate, so we use a recognisable Chrome UA
#: the same way the :mod:`httpx` backend does.  Sites with strict
#: fingerprinting will 403 us regardless.
_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_set_cookie(raw: str) -> SetCookie | None:
    """Parse a single ``Set-Cookie`` header value (best-effort)."""
    raw = (raw or "").strip()
    if not raw or "=" not in raw:
        return None
    name_value, *attrs = raw.split(";")
    name, _, value = name_value.partition("=")
    name = name.strip()
    value = value.strip()
    if not name:
        return None
    kwargs: dict = {"name": name, "value": value}
    for attr in attrs:
        attr = attr.strip()
        if not attr:
            continue
        if "=" in attr:
            key, _, val = attr.partition("=")
            val = val.strip().strip('"')
        else:
            key = attr
            val = ""
        key = key.strip().lower()
        if key == "path":
            kwargs["path"] = val
        elif key == "domain":
            kwargs["domain"] = val
        elif key == "max-age":
            with contextlib.suppress(ValueError):
                kwargs["max_age"] = int(val)
        elif key == "secure":
            kwargs["secure"] = True
        elif key == "httponly":
            kwargs["http_only"] = True
        elif key == "samesite":
            kwargs["same_site"] = val
    return SetCookie(**kwargs)


def _build_opener(cookies: Mapping[str, str] | None) -> urllib.request.OpenerDirector:
    """Construct a fresh :class:`OpenerDirector` with a CookieJar.

    We rebuild the opener per request so the cookies dict from the
    caller is the single source of truth — there is no per-process
    cookie state to leak between sessions.
    """
    jar = http.cookiejar.CookieJar()
    if cookies:
        # Inject caller-provided cookies as ``Cookie`` header equivalents.
        # ``urllib`` will then send them as ``Cookie: k=v; k=v`` via the jar.
        for name, value in cookies.items():
            try:
                cookie = http.cookiejar.Cookie(
                    version=0,
                    name=name,
                    value=str(value),
                    port=None,
                    port_specified=False,
                    domain="",
                    domain_specified=False,
                    domain_initial_dot=False,
                    path="/",
                    path_specified=True,
                    secure=False,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={"HttpOnly": None},
                    rfc2109=False,
                )
                jar.set_cookie(cookie)
            except Exception:  # nosec B110 — best effort
                continue
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _sync_fetch(
    url: str,
    *,
    headers: Mapping[str, str],
    cookies: Mapping[str, str] | None,
    timeout: float,
    follow_redirects: bool,
) -> HttpResponse:
    """Blocking fetch — runs in a worker thread."""
    opener = _build_opener(cookies)
    merged_headers: dict[str, str] = dict(headers)
    if "User-Agent" not in {k.title() for k in merged_headers}:
        merged_headers["User-Agent"] = _DEFAULT_UA

    if not follow_redirects:
        # NoRedirectHandler returns the 3xx response instead of
        # following it.  Caller decides what to do.
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(  # type: ignore[override]
                self,
                req,
                fp,
                code,
                msg,
                headers,
                newurl,
            ):  # noqa: D401
                return None

        opener = urllib.request.build_opener(_NoRedirect())

    req = urllib.request.Request(url, headers=merged_headers, method="GET")
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        # ``HTTPError`` *is* a response — surface its body / headers.
        resp = exc
    except urllib.error.URLError as exc:
        raise HttpBackendError(f"urllib fetch failed: {exc}") from exc
    except Exception as exc:
        raise HttpBackendError(f"urllib fetch failed: {exc}") from exc

    body = resp.read()
    charset = None
    content_type = resp.headers.get("Content-Type") if resp.headers else None
    if content_type:
        # Cheap charset sniff: ``charset=xxx`` is the common case.
        lower = content_type.lower()
        if "charset=" in lower:
            charset = lower.split("charset=", 1)[1].split(";")[0].strip()
    if charset is None:
        charset = "utf-8"
    try:
        text = body.decode(charset, errors="replace")
    except (LookupError, TypeError):
        text = body.decode("utf-8", errors="replace")

    flat_headers: dict[str, str] = {}
    set_cookies: list[SetCookie] = []
    if resp.headers is not None:
        for k, v in resp.headers.items():
            flat_headers[str(k)] = str(v) if v is not None else ""
        for raw in resp.headers.get_all("Set-Cookie") or []:
            parsed = _parse_set_cookie(raw)
            if parsed is not None:
                set_cookies.append(parsed)

    final_url = getattr(resp, "url", url) or url
    status = int(getattr(resp, "status", 200) or 200)

    return HttpResponse(
        url=str(final_url),
        status=status,
        headers=flat_headers,
        text=text,
        set_cookies=set_cookies,
    )


class UrllibBackend:
    """Stdlib-only HTTP backend.  Always available."""

    name = "urllib"

    def is_available(self) -> bool:
        # stdlib: always available in any Python with a working
        # import system.  ``urllib`` is part of CPython's batteries.
        try:
            import urllib.request  # noqa: F401
        except Exception:  # pragma: no cover
            return False
        return True

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
        merged_headers: dict[str, str] = dict(_DEFAULT_HEADERS)
        if headers:
            merged_headers.update(headers)

        # ``urllib`` does not support a max-redirects cap natively; the
        # built-in redirect handler will follow up to whatever the
        # server hands out.  We document this as a known caveat in the
        # skill docs and let the post-redirect SSRF guard in
        # ``server/__init__.py`` catch the worst case.
        try:
            return await asyncio.to_thread(
                _sync_fetch,
                url,
                headers=merged_headers,
                cookies=cookies,
                timeout=timeout,
                follow_redirects=follow_redirects,
            )
        except HttpBackendError:
            raise
        except Exception as exc:
            raise HttpBackendError(f"urllib fetch failed: {exc}") from exc

    async def aclose(self) -> None:
        # No long-lived resources to release.
        return None
