"""Provider registry: dispatch and lazy construction."""

from __future__ import annotations

from collections.abc import Callable

from ..errors import ProviderError
from .base import SearchProvider

_PROVIDER_FACTORIES: dict[str, Callable[[], SearchProvider]] = {}
_PROVIDER_INSTANCES: dict[str, SearchProvider] = {}


def register_provider(name: str, factory: Callable[[], SearchProvider]) -> None:
    """Register a provider factory under ``name``.

    The factory is invoked lazily on first use; tests can override by
    calling :func:`get_provider` after replacing the factory.
    """
    if not name or not isinstance(name, str):
        raise ValueError("Provider name must be a non-empty string.")
    _PROVIDER_FACTORIES[name] = factory
    # Drop any cached instance so the new factory takes effect.
    _PROVIDER_INSTANCES.pop(name, None)


def list_provider_names() -> list[str]:
    """Return all registered provider names (sorted)."""
    return sorted(_PROVIDER_FACTORIES.keys())


def available_providers() -> list[SearchProvider]:
    """Return instances of all currently-registered providers (cached)."""
    out: list[SearchProvider] = []
    for name in list_provider_names():
        try:
            out.append(get_provider(name))
        except ProviderError:
            continue
    return out


def get_provider(name: str) -> SearchProvider:
    """Return a (cached) instance of the named provider.

    Raises:
        ProviderError: when ``name`` is not registered.
    """
    if name in _PROVIDER_INSTANCES:
        return _PROVIDER_INSTANCES[name]
    factory = _PROVIDER_FACTORIES.get(name)
    if factory is None:
        raise ProviderError(
            f"Search provider '{name}' is not registered. "
            f"Available: {', '.join(list_provider_names()) or '(none)'}."
        )
    try:
        instance = factory()
    except Exception as exc:  # pragma: no cover — defensive
        raise ProviderError(f"Failed to construct provider '{name}': {exc}") from exc
    _PROVIDER_INSTANCES[name] = instance
    return instance


#: Eagerly-populated lookup for callers that want the public map.
PROVIDERS: dict[str, SearchProvider] = {}


def _populate_providers() -> None:
    if PROVIDERS:
        return
    for name in list_provider_names():
        try:
            PROVIDERS[name] = get_provider(name)
        except ProviderError:
            continue


def _reset_for_tests() -> None:
    """Test hook: drop cached instances and registrations."""
    _PROVIDER_FACTORIES.clear()
    _PROVIDER_INSTANCES.clear()
    PROVIDERS.clear()
