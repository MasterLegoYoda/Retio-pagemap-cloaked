# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""``httpx``-backed :class:`HttpBackend`.

Pure-Python HTTP client.  No TLS impersonation, so sites with strict
fingerprinting (Cloudflare, Akamai) may still 403 us — that is why
``curl_cffi`` is preferred when it is installed.  ``httpx`` is the
right fallback: a maintained async client with connection pooling,
proper ``Set-Cookie`` parsing, and a small dependency footprint.

The backend owns a single long-lived :class:`httpx.AsyncClient` per
process and reuses it across calls.  Cookies are passed in as a
``name -> value`` dict by the caller (the WebSession) — we do *not*
share a single :class:`httpx.Cookies` across sessions because the
protocol treats cookies as opaque per-session state.
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

#: Per-request default headers.  ``httpx`` does not impersonate, so
#: we use a recognisable-but-boring Chrome UA.  Sites that need real
#: TLS impersonation will reject this — that is what ``curl_cffi`` is
#: for.
_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
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
            with suppress(ValueError):
                kwargs["max_age"] = int(val)
        elif key == "secure":
            kwargs["secure"] = True
        elif key == "httponly":
            kwargs["http_only"] = True
        elif key == "samesite":
            kwargs["same_site"] = val
    return SetCookie(**kwargs)


class HttpxBackend:
    """Async HTTP backend built on :mod:`httpx`."""

    name = "httpx"

    def __init__(self) -> None:
        self._client: Any | None = None
        self._lock = asyncio.Lock()

    def is_available(self) -> bool:
        return importlib.util.find_spec("httpx") is not None

    async def _get_client(self) -> Any:
        async with self._lock:
            if self._client is None:
                try:
                    import httpx  # type: ignore[import-not-found]
                except Exception as exc:  # pragma: no cover
                    raise HttpBackendError(
                        f"httpx is not installed: {exc}"
                    ) from exc
                self._client = httpx.AsyncClient(
                    headers=dict(_DEFAULT_HEADERS),
                    follow_redirects=True,
                    timeout=30.0,
                )
            return self._client

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
            import httpx  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover
            raise HttpBackendError(f"httpx is not installed: {exc}") from exc

        client = await self._get_client()

        merged_headers: dict[str, str] = dict(_DEFAULT_HEADERS)
        if headers:
            merged_headers.update(headers)
        # Don't override the client-level follow_redirects on every
        # call — set up a fresh one-off config instead.
        try:
            response = await client.get(
                url,
                headers=merged_headers,
                cookies=dict(cookies) if cookies else None,
                follow_redirects=follow_redirects,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            raise HttpBackendError(f"httpx fetch failed: {exc}") from exc
        except Exception as exc:
            raise HttpBackendError(f"httpx fetch failed: {exc}") from exc

        flat_headers = {k: str(v) for k, v in response.headers.items()}

        set_cookies: list[SetCookie] = []
        for raw in response.headers.get_list("set-cookie"):
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
            client = self._client
            self._client = None
        if client is None:
            return
        with suppress(Exception):
            await client.aclose()
