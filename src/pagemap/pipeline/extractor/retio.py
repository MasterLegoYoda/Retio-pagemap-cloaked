"""Retio :class:`Extractor` — the existing PageMap core, adapted.

This extractor is the one used by ``get_page_map`` and friends.
It declares every :class:`Capability` bit so the server can
confidently route ``get_page_map`` (which requires ``INTERACTABLES``)
through it.  If a tool needs only a subset of capabilities, the
caller can pick a cheaper extractor (see :class:`PulpieExtractor`).

Attributes:
    name: ``"retio"`` (canonical registry key).
    capabilities: :attr:`Capability.MARKDOWN` |
        :attr:`Capability.INTERACTABLES` | :attr:`Capability.FORMS` |
        :attr:`Capability.PAGE_TYPE` | :attr:`Capability.SCHEMA`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import ExtractedDocument, ExtractorContext
from .capabilities import Capability
from .errors import ExtractorError

if TYPE_CHECKING:
    from pagemap.core import PageMap
    from pagemap.pipeline.retriever.base import FetchedDocument

logger = logging.getLogger(__name__)

_ALL_CAPABILITIES: Capability = (
    Capability.MARKDOWN
    | Capability.INTERACTABLES
    | Capability.FORMS
    | Capability.PAGE_TYPE
    | Capability.SCHEMA
)


class RetioExtractor:
    """Adapt :func:`build_page_map_*` to the pipeline contract.

    When the :class:`FetchedDocument` carries a live Playwright
    :class:`Page` in :attr:`browser_page`, :meth:`extract` calls
    :func:`pagemap.core.page_map_builder.build_page_map_from_page`
    to use the AX tree, DOM guard, and template cache.  Otherwise
    it falls back to :func:`build_page_map_offline` for a static
    HTML-only pass.
    """

    name: str = "retio"
    capabilities: Capability = _ALL_CAPABILITIES

    def is_available(self) -> bool:
        """Always available — no optional dependencies."""
        return True

    async def extract(
        self,
        doc: FetchedDocument,
        ctx: ExtractorContext,
    ) -> ExtractedDocument:
        """Build a :class:`PageMap` and serialize it to markdown-style text.

        Raises:
            ExtractorError: when the input is empty or the build
                fails for a non-network reason.
        """
        if not doc.raw_html and doc.browser_page is None:
            raise ExtractorError(
                "No HTML payload or browser page to extract from."
            )

        # Late import: this pulls in the entire core which is heavy
        # and we want the rest of the pipeline to import quickly.
        from pagemap.core.page_map_builder import (
            build_page_map_from_page,
            build_page_map_offline,
        )
        from pagemap.core.serializer import to_agent_prompt, to_json

        page_map: PageMap | None = None

        if doc.browser_page is not None:
            try:
                page_map = await build_page_map_from_page(
                    doc.browser_page,
                    enable_tier3=True,
                    max_pruned_tokens=int(
                        (ctx.extras or {}).get("max_pruned_tokens", 1500)
                    ),
                    template_cache=ctx.template_cache,
                    spa_signals=ctx.spa_signals,
                )
            except Exception as exc:
                logger.warning("RetioExtractor.build_page_map_from_page failed: %s", exc)
                # Fall back to the offline path when a page is available
                # but the live build blew up (e.g. CDP errors).
                if doc.raw_html:
                    try:
                        page_map = build_page_map_offline(
                            doc.raw_html,
                            url=doc.final_url or "",
                        )
                    except Exception as exc2:  # nosec B110
                        raise ExtractorError(
                            f"RetioExtractor (offline fallback) failed: {exc2}"
                        ) from exc2
                else:
                    raise ExtractorError(f"RetioExtractor failed: {exc}") from exc
        else:
            try:
                page_map = build_page_map_offline(
                    doc.raw_html or "",
                    url=doc.final_url or "",
                )
            except Exception as exc:
                raise ExtractorError(f"RetioExtractor failed: {exc}") from exc

        if page_map is None:
            raise ExtractorError("RetioExtractor produced no PageMap")

        # Serialize.  The default content is the agent-friendly text
        # view; metadata carries the JSON shape for callers that
        # want a structured form.
        try:
            content_text = to_agent_prompt(page_map)
        except Exception as exc:
            content_text = ""
            logger.warning("to_agent_prompt failed: %s", exc)

        try:
            content_json = to_json(page_map)
        except Exception as exc:
            content_json = ""
            logger.warning("to_json failed: %s", exc)

        max_chars = int(ctx.max_chars or 0)
        truncated = False
        full_output_path: str | None = None
        if max_chars > 0 and len(content_text) > max_chars:
            truncated = True
            head = content_text[:max_chars]
            # Spillover is handled by the caller (the server writes
            # the un-truncated text to a temp file).
            content_text = head

        # Build the metadata dict the rest of the server expects.
        warnings: list[str] = list(getattr(page_map, "warnings", []) or [])

        metadata: dict[str, Any] = {
            "extractor": "retio",
            "format": ctx.fmt or "markdown",
            "interactable_count": page_map.total_interactables,
            "tier_counts": page_map.tier_counts,
            "pruned_tokens": page_map.pruned_tokens,
            "generation_ms": page_map.generation_ms,
            "page_type": page_map.page_type,
            "schema": None,
            "images_count": len(page_map.images or []),
            "json": content_json,
        }
        # Surface the page_type / schema on the ExtractedDocument too.
        return ExtractedDocument(
            title=page_map.title or None,
            content=content_text,
            content_length=len(content_text),
            truncated=truncated,
            full_output_path=full_output_path,
            page_type=page_map.page_type,
            schema=None,
            interactables=list(page_map.interactables or []),
            metadata=metadata,
            warnings=warnings,
            page_map=page_map,
        )


__all__ = ["RetioExtractor"]
