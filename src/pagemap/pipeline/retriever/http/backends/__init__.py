# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Built-in :class:`HttpBackend` implementations."""

from .curl_cffi import CurlCffiBackend
from .httpx_backend import HttpxBackend
from .urllib_backend import UrllibBackend

__all__ = [
    "CurlCffiBackend",
    "HttpxBackend",
    "UrllibBackend",
]
