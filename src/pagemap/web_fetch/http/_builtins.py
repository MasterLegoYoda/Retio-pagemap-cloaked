# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Built-in :class:`HttpBackend` implementations.

Importing this module registers ``curl_cffi`` (if installed),
``httpx`` (if installed), and ``urllib`` (always available) with the
:mod:`pagemap.web_fetch.http.registry`.  The default resolution
order — ``curl_cffi`` → ``httpx`` → ``urllib`` — is encoded in
:data:`pagemap.web_fetch.http.registry._AUTO_ORDER`.

Third parties can register additional backends by calling
:func:`pagemap.web_fetch.http.registry.register_backend` with a
factory.  They do not need to be added here.
"""

from __future__ import annotations

from .backends.curl_cffi import CurlCffiBackend
from .backends.httpx_backend import HttpxBackend
from .backends.urllib_backend import UrllibBackend
from .registry import register_backend


def _register_builtins() -> None:
    register_backend("curl_cffi", lambda: CurlCffiBackend())
    register_backend("httpx", lambda: HttpxBackend())
    register_backend("urllib", lambda: UrllibBackend())


_register_builtins()
