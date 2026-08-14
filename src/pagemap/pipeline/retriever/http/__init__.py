# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""HTTP-only fetch backends for ``web_fetch`` ``mode="fast"``.

This package isolates the "simple" HTTP transport from the rest of
``pagemap.web_fetch`` so that a new backend (e.g. ``cycletls``,
``tls-client``) can be plugged in via :func:`register_backend` without
touching tool or extraction code.

Public surface:

* :class:`HttpBackend` — the protocol every backend implements.
* :class:`HttpResponse` — uniform response shape.
* :func:`get_backend` / :func:`list_backends` / :func:`resolve_backend` —
  registry access.
* :func:`register_backend` — third-party extension point.

Backends are registered in :mod:`pagemap.web_fetch.http._builtins`. The
default order (used by ``resolve_backend("auto")``) is:

1. ``curl_cffi`` — TLS-impersonating HTTP client (Chrome/Safari
   fingerprints).  Preferred when available.
2. ``httpx`` — pure-Python fallback with no TLS impersonation but good
   connection pooling.
3. ``urllib`` — stdlib fallback, always available.
"""

from __future__ import annotations

from . import _builtins  # noqa: F401  (side effect: registers built-in backends)
from .base import HttpBackend, HttpResponse, SetCookie
from .registry import (
    get_backend,
    list_backends,
    register_backend,
    resolve_backend,
)

__all__ = [
    "HttpBackend",
    "HttpResponse",
    "SetCookie",
    "get_backend",
    "list_backends",
    "register_backend",
    "resolve_backend",
]
