"""The :class:`Pipeline` — pairs a :class:`Retriever` with an :class:`Extractor`.

A :class:`Pipeline` is the smallest unit a tool needs to fetch a
URL and turn it into an LLM-readable document.  Server-side code
configures one :class:`Pipeline` at startup (via the CLI / env) and
re-uses it for every call.

Why a single class for the pair (rather than just calling
``retriever.fetch`` then ``extractor.extract``)?

* It carries the configuration that both halves share
  (e.g. :attr:`name`, :attr:`capabilities`).
* It makes the capability bitmask a single value the rest of the
  server can pre-flight check.
* It allows :class:`~pagemap.pipeline.core.Pipeline` to be
  registered and looked up by name in the named-pipeline registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .extractor import ExtractedDocument, Extractor, ExtractorContext
from .extractor.capabilities import Capability
from .extractor.errors import MissingCapability
from .retriever import FetchContext, FetchedDocument, Retriever


@dataclass
class Pipeline:
    """A paired :class:`Retriever` + :class:`Extractor`.

    Attributes:
        name: The registry key for this pipeline (e.g.
            ``"cloak-retio"``).  Unique across the named-pipeline
            registry.
        retriever: The transport.
        extractor: The content transformer.
    """

    name: str
    retriever: Retriever
    extractor: Extractor
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def capabilities(self) -> Capability:
        """Return the capability bitmask advertised by the extractor."""
        return self.extractor.capabilities

    def has_capability(self, cap: Capability) -> bool:
        """Return ``True`` iff the extractor's capabilities include ``cap``."""
        if not isinstance(cap, Capability):
            cap = Capability(int(cap))
        return cap in self.capabilities

    def require_capability(
        self,
        cap: Capability,
        *,
        tool: str | None = None,
        hint: str | None = None,
    ) -> None:
        """Raise :class:`MissingCapability` if ``cap`` is not advertised.

        Tools call this at the top of their implementation to fail
        fast with a readable error before doing any work.
        """
        if self.has_capability(cap):
            return
        raise MissingCapability(
            pipeline_name=self.name,
            extractor_name=self.extractor.name,
            capability=int(cap),
            tool=tool,
            hint=hint,
        )

    async def run(
        self,
        url: str,
        *,
        fetch_ctx: FetchContext | None = None,
        extract_ctx: ExtractorContext | None = None,
    ) -> ExtractedDocument:
        """Fetch ``url`` and extract content from it.

        Steps:
            1. ``await self.retriever.fetch(url, ctx=fetch_ctx)``
            2. ``await self.extractor.extract(doc, ctx=extract_ctx)``

        The fetch and extract contexts default to empty ones — pass
        them when you need to carry cookies, headers, format hints,
        etc.
        """
        fctx = fetch_ctx or FetchContext()
        ectx = extract_ctx or ExtractorContext()
        doc: FetchedDocument = await self.retriever.fetch(url, ctx=fctx)
        return await self.extractor.extract(doc, ectx)


__all__ = ["Pipeline"]
