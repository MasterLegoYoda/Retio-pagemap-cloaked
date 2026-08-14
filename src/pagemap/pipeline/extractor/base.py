"""Protocols and value objects for :mod:`pagemap.pipeline.extractor`.

* :class:`Extractor` — turns a :class:`FetchedDocument` (raw HTML plus
  transport metadata) into a :class:`ExtractedDocument` (content,
  title, optional :class:`pagemap.core.PageMap`).

Adding a new extractor is a two-step process:

1.  Subclass or duck-type :class:`Extractor` in a module under
    :mod:`pagemap.pipeline.extractor`.
2.  Call :func:`pagemap.pipeline.extractor.register_extractor` with a
    factory (typically ``lambda: MyExtractor()``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pagemap.pipeline.retriever.base import FetchedDocument

    from .capabilities import Capability


@dataclass
class ExtractorContext:
    """Per-call context handed to an :class:`Extractor`.

    Attributes:
        max_chars: Truncation limit for the body.  ``<=0`` disables.
        fmt: Output format (``markdown`` | ``text`` | ``html`` | ``json``).
            Some extractors (pulpie, retio) may ignore this; the
            :class:`~pagemap.pipeline.extractor.markdown.MarkdownExtractor`
            honours all four.
        template_cache: Optional :class:`InMemoryTemplateCache` for
            :class:`RetioExtractor`.  Other extractors ignore it.
        timer: Optional :class:`PipelineTimer` for staged metrics.
        task_hint: ``"search" | "detail" | "cart" | "form" | "general"``
            passed to the PageMap builder.  ``None`` for the default
            pruning profile.
        cached: A pre-fetched result to merge into, when the caller is
            doing a partial refresh.  ``None`` for fresh calls.
        spa_signals: Optional SPA / hydration signals to pass through
            to the PageMap builder.
        model: Implementation-specific model object (e.g. the loaded
            Pulpie :class:`pulpie.Extractor`).
        extras: Implementation-specific extras (e.g. proxy config,
            image proxy, locale, custom task hints).
    """

    max_chars: int = 50_000
    fmt: str = "markdown"
    template_cache: Any | None = None
    timer: Any | None = None
    task_hint: str | None = None
    cached: dict | None = None
    spa_signals: dict | None = None
    model: Any | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedDocument:
    """Result of a single :class:`Extractor` invocation.

    Attributes:
        title: Page title, when known.
        content: The extracted content.  For extractors that emit
            markdown (``MARKDOWN`` capability), this is the markdown
            body.  For ``RetioExtractor`` this is the agent-optimized
            prompt-style serialization.
        content_length: ``len(content)`` (computed at the source so
            downstream code can stay simple).
        truncated: ``True`` when ``content`` was truncated to fit
            ``max_chars``.  The un-truncated text is at
            ``full_output_path`` when set.
        full_output_path: Path to a spillover file containing the
            un-truncated text.  ``None`` when not truncated.
        page_type: Page classification (when the extractor advertises
            :attr:`~pagemap.pipeline.extractor.capabilities.Capability.PAGE_TYPE`).
        schema: Schema name (when the extractor advertises
            :attr:`~pagemap.pipeline.extractor.capabilities.Capability.SCHEMA`).
        interactables: Ref-numbered interactables (when the extractor
            advertises
            :attr:`~pagemap.pipeline.extractor.capabilities.Capability.INTERACTABLES`).
        metadata: Extractor-specific structured data (e.g. retio
            metadata, pulpie ``n_main`` / ``n_other`` counts).
        warnings: Non-fatal warnings (e.g. "form fields not preserved").
        page_map: The rich :class:`PageMap` for ``RetioExtractor``;
            ``None`` for the simpler extractors.
    """

    title: str | None
    content: str
    content_length: int
    truncated: bool
    full_output_path: str | None
    page_type: str | None = None
    schema: str | None = None
    interactables: list | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    page_map: Any | None = None  # PageMap | None — avoid hard import cycle


@runtime_checkable
class Extractor(Protocol):
    """Pluggable transformer that turns a :class:`FetchedDocument` into a :class:`ExtractedDocument`.

    Implementations should be cheap to construct.  All per-call state
    (max_chars, format, model object) is passed in via
    :class:`ExtractorContext`.
    """

    #: Canonical extractor name (matches the registry key).
    name: str

    #: Bitmask of :class:`Capability` bits the extractor advertises.
    capabilities: Capability

    def is_available(self) -> bool:
        """Return ``True`` if this extractor can be used right now.

        Implementations that need an optional dependency (e.g.
        :class:`PulpieExtractor` needs the ``pulpie`` package) should
        return ``False`` when the dependency is missing.
        """
        ...

    async def extract(
        self,
        doc: FetchedDocument,
        ctx: ExtractorContext,
    ) -> ExtractedDocument:
        """Extract content from ``doc`` and return a :class:`ExtractedDocument`.

        Raises:
            ExtractorError: on extraction failures.
        """
        ...


__all__ = [
    "ExtractedDocument",
    "Extractor",
    "ExtractorContext",
]
