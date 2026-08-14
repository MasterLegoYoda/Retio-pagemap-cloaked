"""Registry of :class:`Retriever` factories.

Retrievers register themselves by name and are looked up lazily.  The
default resolution order for ``resolve_retriever("auto")`` is
``cloak -> fetch`` so the most capable available retriever wins.
"""

from __future__ import annotations

from collections.abc import Callable

from .base import Retriever, RetrieverError, RetrieverNotFound

_FACTORIES: dict[str, Callable[[], Retriever]] = {}
_INSTANCES: dict[str, Retriever] = {}
_AUTO_ORDER: tuple[str, ...] = ("cloak", "fetch")


def register_retriever(name: str, factory: Callable[[], Retriever]) -> None:
    """Register ``factory`` under ``name``.

    Calling this twice for the same name replaces the previous factory;
    any cached instance is dropped.
    """
    if not name or not isinstance(name, str):
        raise ValueError("Retriever name must be a non-empty string.")
    _FACTORIES[name] = factory
    _INSTANCES.pop(name, None)


def list_retrievers() -> list[str]:
    """Return the names of all registered retrievers, sorted."""
    return sorted(_FACTORIES.keys())


def get_retriever(name: str) -> Retriever:
    """Return a (cached) :class:`Retriever` instance by name.

    Raises:
        RetrieverNotFound: when ``name`` is not registered.
        RetrieverError: when the factory raises or the retriever
            reports itself unavailable.
    """
    if name in _INSTANCES:
        return _INSTANCES[name]
    factory = _FACTORIES.get(name)
    if factory is None:
        raise RetrieverNotFound(name, available=list_retrievers())
    try:
        instance = factory()
    except Exception as exc:
        raise RetrieverError(f"Failed to construct retriever '{name}': {exc}") from exc
    if not instance.is_available():
        raise RetrieverError(
            f"Retriever '{name}' is registered but reports itself as unavailable. "
            f"Check the optional dependency or runtime environment."
        )
    _INSTANCES[name] = instance
    return instance


def resolve_retriever(prefer: str | None = None) -> Retriever:
    """Return the best available retriever.

    Args:
        prefer: Retriever name to use if available. Special values:
            ``None`` / ``"auto"`` — pick the first available in
            :data:`_AUTO_ORDER`.  Any other string is forwarded to
            :func:`get_retriever`.

    Raises:
        RetrieverError: when no retriever can be resolved.
    """
    if prefer and prefer != "auto":
        return get_retriever(prefer)

    last_error: RetrieverError | None = None
    for name in _AUTO_ORDER:
        if name not in _FACTORIES:
            continue
        try:
            return get_retriever(name)
        except RetrieverError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise RetrieverError(
            f"No retriever available. Tried {', '.join(_AUTO_ORDER)}; last error: {last_error}"
        ) from last_error
    raise RetrieverError(
        "No retrievers are registered. "
        "Import pagemap.pipeline to trigger built-in registration."
    )


def _reset_for_tests() -> None:
    """Test hook: drop cached instances and registrations."""
    _FACTORIES.clear()
    _INSTANCES.clear()
