"""Registry of named :class:`Pipeline` instances.

A *named pipeline* is a stable string (``"cloak-retio"``,
``"fetch-pulpie"``) that the user picks at startup.  The registry
maps each name to a factory that builds the right
:class:`Retriever` + :class:`Extractor` pair, lazily on first use.

Resolution rules
----------------

* Exact name → return that pipeline.
* ``"<retriever>-<extractor>"`` (e.g. ``"fetch-markdown"``) → build
  the pair on the fly.  Returns the pair even if the same name was
  not pre-registered, as long as both halves resolve.
* Falls through to the named-pipeline lookup otherwise.
"""

from __future__ import annotations

from collections.abc import Callable

from .core import Pipeline
from .extractor import ExtractorError, ExtractorNotFound, list_extractors
from .extractor.registry import get_extractor
from .retriever import RetrieverError, RetrieverNotFound, list_retrievers
from .retriever.registry import get_retriever

#: Factory: produces a fresh :class:`Pipeline` instance.  Invoked
#: lazily on first use so optional-dependency imports happen at
#: call time, not at import time.
_PIPELINE_FACTORIES: dict[str, Callable[[], Pipeline]] = {}
_PIPELINE_INSTANCES: dict[str, Pipeline] = {}


class PipelineNotFound(KeyError):
    """No pipeline matches the requested name or combination."""

    def __init__(self, name: str, *, available: list[str] | None = None) -> None:
        self.name = name
        self.available = available or []
        super().__init__(name)

    def __str__(self) -> str:  # pragma: no cover — formatting
        if self.available:
            return f"Pipeline '{self.name}' is not registered. Available: {', '.join(self.available)}."
        return f"Pipeline '{self.name}' is not registered."


def register_pipeline(name: str, factory: Callable[[], Pipeline]) -> None:
    """Register a named pipeline factory under ``name``.

    The factory is invoked lazily on first :func:`get_pipeline` call.
    """
    if not name or not isinstance(name, str):
        raise ValueError("Pipeline name must be a non-empty string.")
    _PIPELINE_FACTORIES[name] = factory
    _PIPELINE_INSTANCES.pop(name, None)


def register_named_pair(retriever_name: str, extractor_name: str) -> str:
    """Convenience: register a pipeline that pairs two existing
    registry entries by name.

    Returns the pipeline name (same as ``f"{retriever_name}-{extractor_name}"``).
    The pipeline is built lazily by calling :func:`get_retriever`
    and :func:`get_extractor` on first use, so registering many
    pairs is cheap.
    """
    name = f"{retriever_name}-{extractor_name}"
    register_pipeline(name, lambda: _build_pair(name, retriever_name, extractor_name))
    return name


def _build_pair(name: str, retriever_name: str, extractor_name: str) -> Pipeline:
    retriever = get_retriever(retriever_name)
    extractor = get_extractor(extractor_name)
    return Pipeline(name=name, retriever=retriever, extractor=extractor)


def list_pipelines() -> list[str]:
    """Return all named pipeline names, sorted."""
    return sorted(_PIPELINE_FACTORIES.keys())


def get_pipeline(name: str) -> Pipeline:
    """Return a (cached) named :class:`Pipeline` by exact name.

    Raises:
        PipelineNotFound: when ``name`` is not registered.
        RetrieverError / ExtractorError: when one of the halves fails.
    """
    if name in _PIPELINE_INSTANCES:
        return _PIPELINE_INSTANCES[name]
    factory = _PIPELINE_FACTORIES.get(name)
    if factory is None:
        raise PipelineNotFound(name, available=list_pipelines())
    try:
        instance = factory()
    except (RetrieverError, ExtractorError):
        raise
    except Exception as exc:
        raise PipelineNotFound(
            f"Failed to construct pipeline '{name}': {exc}"
        ) from exc
    _PIPELINE_INSTANCES[name] = instance
    return instance


def _looks_like_pair(name: str) -> tuple[str, str] | None:
    """Heuristic: split ``"<retriever>-<extractor>"`` if both halves
    resolve.  Returns ``None`` if either half is unknown, so the
    caller can fall through to the named-pipeline lookup.
    """
    if "-" not in name:
        return None
    head, _, tail = name.partition("-")
    if not head or not tail:
        return None
    if head not in list_retrievers() or tail not in list_extractors():
        return None
    return head, tail


def resolve_pipeline(name: str) -> Pipeline:
    """Resolve a :class:`Pipeline` from the registry.

    Resolution order:

    1.  ``name`` matches a named pipeline → return it.
    2.  ``name`` looks like ``"<retriever>-<extractor>"`` → build
        the pair and return it (also registers the pair for future
        lookups).
    3.  Else raise :class:`PipelineNotFound`.
    """
    if name in _PIPELINE_FACTORIES:
        return get_pipeline(name)

    pair = _looks_like_pair(name)
    if pair is not None:
        retriever_name, extractor_name = pair
        try:
            pipeline = _build_pair(name, retriever_name, extractor_name)
        except (RetrieverNotFound, ExtractorNotFound) as exc:
            raise PipelineNotFound(name, available=list_pipelines()) from exc
        # Cache for subsequent lookups.
        _PIPELINE_INSTANCES[name] = pipeline
        return pipeline

    raise PipelineNotFound(name, available=list_pipelines())


def list_pipelines_with_capability(cap) -> list[str]:
    """Return the names of named pipelines whose extractor advertises ``cap``.

    Always returns pairs (e.g. ``"cloak-retio"``) over arbitrary
    user-registered names because the cartesian product is
    implicitly available via :func:`resolve_pipeline`.  Names that
    don't match a known retriever/extractor are filtered out.
    """
    from .extractor.capabilities import Capability

    if not isinstance(cap, Capability):
        cap = Capability(int(cap))

    out: list[str] = []
    for r in list_retrievers():
        for e in list_extractors():
            try:
                pipeline = _build_pair(f"{r}-{e}", r, e)
            except Exception:  # nosec B110
                continue
            if cap in pipeline.capabilities:
                out.append(f"{r}-{e}")
    # Include any pre-registered pipelines that match.
    for name in _PIPELINE_FACTORIES:
        if "-" in name:
            continue  # already covered by the cartesian product
        try:
            pipeline = get_pipeline(name)
        except Exception:  # nosec B110
            continue
        if cap in pipeline.capabilities:
            out.append(name)
    return sorted(set(out))


def _reset_for_tests() -> None:
    """Test hook: drop cached instances and registrations.

    Tests should snapshot the registries before mutating and call
    :func:`_register_builtins` from
    :mod:`pagemap.pipeline._builtins` to repopulate.
    """
    _PIPELINE_FACTORIES.clear()
    _PIPELINE_INSTANCES.clear()


__all__ = [
    "PipelineNotFound",
    "get_pipeline",
    "list_pipelines",
    "list_pipelines_with_capability",
    "register_named_pair",
    "register_pipeline",
    "resolve_pipeline",
]
