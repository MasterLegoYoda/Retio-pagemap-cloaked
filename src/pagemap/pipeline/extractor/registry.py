"""Registry of :class:`Extractor` factories.

Extractors register themselves by name and are looked up lazily.  The
default resolution order for ``resolve_extractor("auto")`` is
``retio -> pulpie -> markdown`` so the most capable available
extractor wins.
"""

from __future__ import annotations

from collections.abc import Callable

from .base import ExtractedDocument, Extractor, ExtractorContext
from .errors import ExtractorError, ExtractorNotFound

_FACTORIES: dict[str, Callable[[], Extractor]] = {}
_INSTANCES: dict[str, Extractor] = {}
_AUTO_ORDER: tuple[str, ...] = ("retio", "pulpie", "markdown")


def register_extractor(name: str, factory: Callable[[], Extractor]) -> None:
    """Register ``factory`` under ``name``.

    Calling this twice for the same name replaces the previous
    factory; any cached instance is dropped.
    """
    if not name or not isinstance(name, str):
        raise ValueError("Extractor name must be a non-empty string.")
    _FACTORIES[name] = factory
    _INSTANCES.pop(name, None)


def list_extractors() -> list[str]:
    """Return the names of all registered extractors, sorted."""
    return sorted(_FACTORIES.keys())


def get_extractor(name: str) -> Extractor:
    """Return a (cached) :class:`Extractor` instance by name.

    Raises:
        ExtractorNotFound: when ``name`` is not registered.
        ExtractorError: when the factory raises or the extractor
            reports itself unavailable.
    """
    if name in _INSTANCES:
        return _INSTANCES[name]
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ExtractorNotFound(name, available=list_extractors())
    try:
        instance = factory()
    except Exception as exc:
        raise ExtractorError(f"Failed to construct extractor '{name}': {exc}") from exc
    if not instance.is_available():
        raise ExtractorError(
            f"Extractor '{name}' is registered but reports itself as unavailable. "
            f"Check the optional dependency (e.g. pip install 'retio-pagemap[{name}]')."
        )
    _INSTANCES[name] = instance
    return instance


def resolve_extractor(prefer: str | None = None) -> Extractor:
    """Return the best available extractor.

    Args:
        prefer: Extractor name to use if available.  Special values:
            ``None`` / ``"auto"`` — pick the first available in
            :data:`_AUTO_ORDER`.  Any other string is forwarded to
            :func:`get_extractor`.

    Raises:
        ExtractorError: when no extractor can be resolved.
    """
    if prefer and prefer != "auto":
        return get_extractor(prefer)

    last_error: ExtractorError | None = None
    for name in _AUTO_ORDER:
        if name not in _FACTORIES:
            continue
        try:
            return get_extractor(name)
        except ExtractorError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise ExtractorError(
            f"No extractor available. Tried {', '.join(_AUTO_ORDER)}; last error: {last_error}"
        ) from last_error
    raise ExtractorError(
        "No extractors are registered. "
        "Import pagemap.pipeline to trigger built-in registration."
    )


def _reset_for_tests() -> None:
    """Test hook: drop cached instances and registrations."""
    _FACTORIES.clear()
    _INSTANCES.clear()


__all__ = [
    "ExtractedDocument",
    "Extractor",
    "ExtractorContext",
    "ExtractorError",
    "ExtractorNotFound",
    "get_extractor",
    "list_extractors",
    "register_extractor",
    "resolve_extractor",
]
