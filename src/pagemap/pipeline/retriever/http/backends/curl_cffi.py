# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""``curl_cffi``-backed :class:`HttpBackend`.

``curl_cffi`` uses a bundled libcurl-impersonate to perform TLS
handshakes that match real Chrome / Safari / Edge fingerprints.  That
is exactly what we need for ``web_fetch`` fast mode: many sites
served by Cloudflare / Akamai shape their bot detection on the TLS
fingerprint, and a vanilla ``httpx`` or ``urllib`` request looks like
a bot to them.  ``curl_cffi`` is therefore the preferred backend
whenever it is installed (``pip install 'retio-pagemap[fast]'``).

The implementation is deliberately thin: it wraps
``curl_cffi.AsyncSession`` (which is a true async client, unlike the
synchronous ``curl_cffi.Session`` that would force us onto
``asyncio.to_thread``).  The async session supports connection
pooling, ``allow_redirects``, custom headers, and cookies.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from ..base import HttpBackendError, HttpResponse, SetCookie

logger = logging.getLogger(__name__)

#: Default impersonation target.  ``curl_cffi`` maps this to the most
#: recent Chrome build its libcurl-impersonate copy supports, so we
#: stay current without pinning a version.
_DEFAULT_IMPERSONATE = "chrome"

#: Per-request default headers — we keep the set deliberately small.
#: ``curl_cffi`` adds its own impersonation headers (Sec-CH-*, etc.)
#: when ``impersonate=`` is set, so we only need to fill in the gaps.
_DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_set_cookie(raw: str) -> SetCookie | None:
    """Parse a single ``Set-Cookie`` header value.

    Returns ``None`` when the header is malformed; callers should
    silently drop it.  Only the simple ``name=value`` pair is required
    for the bot-detection bypass use case — ``path``/``domain``/
    ``expires``/etc. are surfaced for completeness but the session
    merger ignores them.
    """
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
        elif key == "expires":
            # Best-effort: don't bother parsing the date — fast mode
            # treats the cookie as session-scoped anyway.
            continue
        elif key == "max-age":
            with suppress(ValueError):
                kwargs["max_age"] = int(val)
        elif key == "secure":
            kwargs["secure"] = True
        elif key == "httponly":
            kwargs["http_only"] = True
        elif key == "samesite":
            kwargs["same_site"] = val
    return SetCookie(**kwargs)


def _cookies_to_jar(cookies: Any) -> dict[str, str]:
    """Flatten a ``RequestsCookieJar`` / ``SimpleCookie`` / ``Cookies`` to ``{name: value}``."""
    out: dict[str, str] = {}
    if cookies is None:
        return out
    try:
        for c in cookies:
            name = getattr(c, "name", None) or c.key
            value = getattr(c, "value", None)
            if name and value is not None:
                out[name] = value
    except TypeError:
        # Mapping-like (httpx.Cookies, dict).
        try:
            for k, v in dict(cookies).items():
                out[str(k)] = str(v)
        except Exception:  # nosec B110
            pass
    return out


class CurlCffiBackend:
    """Async HTTP backend that impersonates a real browser's TLS fingerprint."""

    name = "curl_cffi"

    def __init__(self) -> None:
        self._session: Any | None = None
        self._lock = asyncio.Lock()

    def is_available(self) -> bool:
        return importlib.util.find_spec("curl_cffi") is not None

    async def _get_session(self, impersonate: str | None) -> Any:
        """Return a long-lived :class:`AsyncSession`.

        Re-created when the requested ``impersonate`` value changes so
        callers can override it per-call without leaking sessions.
        """
        target = impersonate or _DEFAULT_IMPERSONATE
        async with self._lock:
            sess = self._session
            if sess is not None and getattr(sess, "_pagemap_impersonate", None) == target:
                return sess
            if sess is not None:
                with suppress(Exception):
                    await sess.aclose()
            try:
                from curl_cffi import AsyncSession  # type: ignore[import-not-found]
            except Exception as exc:  # pragma: no cover — is_available() guards
                raise HttpBackendError(
                    f"curl_cffi is not installed: {exc}. "
                    "Install with `pip install 'retio-pagemap[fast]'`."
                ) from exc
            sess = AsyncSession(impersonate=target, headers=_DEFAULT_HEADERS)
            sess._pagemap_impersonate = target
            self._session = sess
            return sess

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
        try:
            from curl_cffi.requests.exceptions import (  # type: ignore[import-not-found]
                RequestException,
            )
        except Exception as exc:  # pragma: no cover
            raise HttpBackendError(f"curl_cffi import failed: {exc}") from exc

        sess = await self._get_session(impersonate)

        merged_headers: dict[str, str] = dict(_DEFAULT_HEADERS)
        if headers:
            merged_headers.update(headers)

        cookie_dict = dict(cookies) if cookies else None

        try:
            response = await sess.get(
                url,
                headers=merged_headers,
                cookies=cookie_dict,
                allow_redirects=follow_redirects,
                max_redirects=max_redirects,
                timeout=timeout,
            )
        except RequestException as exc:
            raise HttpBackendError(f"curl_cffi fetch failed: {exc}") from exc
        except Exception as exc:
            raise HttpBackendError(f"curl_cffi fetch failed: {exc}") from exc

        # curl_cffi's response headers are a case-insensitive mapping.
        flat_headers: dict[str, str] = {}
        try:
            for k, v in dict(response.headers).items():
                flat_headers[str(k)] = str(v) if v is not None else ""
        except Exception:  # nosec B110
            pass

        # Surface set-cookies from both the response and the session,
        # so the caller can merge them into the WebSession's jar.
        set_cookies: list[SetCookie] = []
        raw_set_cookies = []
        try:
            raw_set_cookies = list(response.headers.get_list("set-cookie"))
        except Exception:
            try:
                for c in response.cookies or ():
                    raw = f"{c.name}={c.value}"
                    if getattr(c, "path", None):
                        raw += f"; Path={c.path}"
                    if getattr(c, "secure", False):
                        raw += "; Secure"
                    raw_set_cookies.append(raw)
            except Exception:  # nosec B110
                raw_set_cookies = []
        for raw in raw_set_cookies:
            parsed = _parse_set_cookie(raw)
            if parsed is not None:
                set_cookies.append(parsed)

        return HttpResponse(
            url=str(response.url),
            status=int(response.status_code),
            headers=flat_headers,
            text=str(response.text or ""),
            set_cookies=set_cookies,
        )

    async def aclose(self) -> None:
        async with self._lock:
            sess = self._session
            self._session = None
        if sess is None:
            return
        with suppress(Exception):
            await sess.aclose()
