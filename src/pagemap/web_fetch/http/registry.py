# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Registry of HTTP backends.

Backends register themselves by name and are looked up lazily.  The
default resolution order for ``resolve_backend("auto")`` is:

    curl_cffi -> httpx -> urllib

so the most capable backend available wins.
"""

from __future__ import annotations

from collections.abc import Callable

from .base import HttpBackend, HttpBackendError

#: Factory: produces a fresh backend instance.  Invoked lazily on
#: first use so optional-dependency imports happen at call time, not
#: at import time.
_FACTORIES: dict[str, Callable[[], HttpBackend]] = {}

#: Cached backend instances.  Cleared on ``register_backend`` so the
#: latest factory wins.
_INSTANCES: dict[str, HttpBackend] = {}

#: Default fallback order for ``resolve_backend("auto")``.  Backends
#: not registered or not available are skipped.
_AUTO_ORDER: tuple[str, ...] = ("curl_cffi", "httpx", "urllib")


def register_backend(name: str, factory: Callable[[], HttpBackend]) -> None:
    """Register ``factory`` under ``name``.

    Calling this twice for the same name replaces the previous
    factory; any cached instance is dropped.
    """
    if not name or not isinstance(name, str):
        raise ValueError("Backend name must be a non-empty string.")
    _FACTORIES[name] = factory
    _INSTANCES.pop(name, None)


def list_backends() -> list[str]:
    """Return the names of all registered backends, sorted."""
    return sorted(_FACTORIES.keys())


def get_backend(name: str) -> HttpBackend:
    """Return a (cached) :class:`HttpBackend` instance by name.

    Raises:
        HttpBackendError: when ``name`` is not registered or the
            backend's optional dependency is not installed.
    """
    if name in _INSTANCES:
        return _INSTANCES[name]
    factory = _FACTORIES.get(name)
    if factory is None:
        raise HttpBackendError(
            f"HTTP backend '{name}' is not registered. "
            f"Available: {', '.join(list_backends()) or '(none)'}."
        )
    try:
        instance = factory()
    except Exception as exc:  # pragma: no cover — defensive
        raise HttpBackendError(
            f"Failed to construct HTTP backend '{name}': {exc}"
        ) from exc
    if not instance.is_available():
        raise HttpBackendError(
            f"HTTP backend '{name}' is registered but its optional dependency "
            f"is not installed. Install it to enable this backend."
        )
    _INSTANCES[name] = instance
    return instance


def resolve_backend(prefer: str | None = None) -> HttpBackend:
    """Return the best available backend.

    Args:
        prefer: Backend name to use if available.  Special values:
            ``None`` / ``"auto"`` — pick the first available in
            :data:`_AUTO_ORDER`.  Any other string is forwarded to
            :func:`get_backend`.

    Raises:
        HttpBackendError: when no backend can be resolved.
    """
    if prefer and prefer != "auto":
        return get_backend(prefer)

    last_error: HttpBackendError | None = None
    for name in _AUTO_ORDER:
        if name not in _FACTORIES:
            continue
        try:
            return get_backend(name)
        except HttpBackendError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise HttpBackendError(
            "No HTTP backend available. Tried "
            f"{', '.join(_AUTO_ORDER)}; last error: {last_error}"
        ) from last_error
    raise HttpBackendError(
        "No HTTP backends are registered. "
        "Import pagemap.web_fetch.http to trigger built-in registration."
    )


def _reset_for_tests() -> None:
    """Test hook: drop cached instances and registrations."""
    _FACTORIES.clear()
    _INSTANCES.clear()
