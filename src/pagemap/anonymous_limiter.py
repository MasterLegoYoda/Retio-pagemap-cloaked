"""Backward-compat shim — import from pagemap.cloud.anonymous_limiter instead."""

from pagemap.cloud.anonymous_limiter import (  # noqa: F401
    AnonymousCheckResult,
    AnonymousLimiter,
)

__all__ = [
    "AnonymousCheckResult",
    "AnonymousLimiter",
]
