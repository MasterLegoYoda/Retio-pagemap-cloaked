"""Pluggable retriever + extractor pipeline for PageMap.

A :class:`~pagemap.pipeline.core.Pipeline` pairs a :class:`Retriever`
(transport) with an :class:`Extractor` (content extraction) and exposes a
single :meth:`Pipeline.run` entry point plus a :meth:`Pipeline.capabilities`
bitmask derived from the extractor.

Adding a new backend is a two-step process:

1.  Subclass or duck-type :class:`Retriever` /
    :class:`Extractor` in a module under
    :mod:`pagemap.pipeline.retriever` or
    :mod:`pagemap.pipeline.extractor`.
2.  Call :func:`register_retriever` /
    :func:`register_extractor` (and optionally
    :func:`register_pipeline`) with a factory.

The protocols are deliberately small. Anything that needs richer
transport hooks (cookie persistence, per-call headers, etc.) is
threaded through :class:`FetchContext` / :class:`ExtractorContext` as
plain attributes — no plugin API to learn.
"""

from __future__ import annotations

from . import _builtins  # noqa: F401  (side effect: registers built-ins)
from .config import PipelineConfig, resolve_config
from .core import Pipeline
from .extractor import (
    Capability,
    ExtractedDocument,
    Extractor,
    ExtractorContext,
    ExtractorError,
    ExtractorNotFound,
    MissingCapability,
    list_extractors,
    register_extractor,
)
from .registry import (
    PipelineNotFound,
    get_pipeline,
    list_pipelines,
    register_pipeline,
    resolve_pipeline,
)
from .retriever import (
    FetchContext,
    FetchedDocument,
    Retriever,
    RetrieverError,
    RetrieverNotFound,
    list_retrievers,
    register_retriever,
)

__all__ = [
    "Capability",
    "ExtractedDocument",
    "Extractor",
    "ExtractorContext",
    "ExtractorError",
    "ExtractorNotFound",
    "FetchContext",
    "FetchedDocument",
    "MissingCapability",
    "Pipeline",
    "PipelineConfig",
    "PipelineNotFound",
    "Retriever",
    "RetrieverError",
    "RetrieverNotFound",
    "get_pipeline",
    "list_extractors",
    "list_pipelines",
    "list_retrievers",
    "register_extractor",
    "register_pipeline",
    "register_retriever",
    "resolve_config",
    "resolve_pipeline",
]
