"""Markdown-only :class:`Extractor`.

Thin adapter around :func:`pagemap.pipeline.extractor._html_utils.extract`.
This preserves the byte-identical output of the pre-refactor
``_extract_content`` call inside ``_web_fetch_impl`` so existing
tool consumers see no change in tool output.

Capability bitmask: :attr:`Capability.MARKDOWN` only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ._html_utils import extract as _extract
from .base import ExtractedDocument, ExtractorContext
from .capabilities import Capability
from .errors import ExtractorError

if TYPE_CHECKING:
    from pagemap.pipeline.retriever.base import FetchedDocument

logger = logging.getLogger(__name__)


class MarkdownExtractor:
    """Convert raw HTML to markdown / text / html / json.

    This is the cheap, always-available default.  No JS, no model, no
    network — just BeautifulSoup + a small renderer.  Use it when you
    want a fast read-only fetch with predictable output, regardless of
    the page's structure.

    Attributes:
        name: ``"markdown"`` (canonical registry key).
        capabilities: :attr:`Capability.MARKDOWN` only.
    """

    name: str = "markdown"
    capabilities: Capability = Capability.MARKDOWN

    def is_available(self) -> bool:
        """Always available — no optional dependencies."""
        return True

    async def extract(
        self,
        doc: FetchedDocument,
        ctx: ExtractorContext,
    ) -> ExtractedDocument:
        """Run the :func:`extract` helper on the raw HTML."""
        if not doc.raw_html:
            raise ExtractorError("No HTML payload to extract from.")

        fmt = ctx.fmt or "markdown"
        max_chars = int(ctx.max_chars or 0)
        try:
            extracted = _extract(
                raw_html=doc.raw_html,
                url=doc.final_url or "",
                fmt=fmt,
                max_chars=max_chars,
            )
        except Exception as exc:
            raise ExtractorError(f"Markdown extraction failed: {exc}") from exc

        return ExtractedDocument(
            title=extracted.title,
            content=extracted.content,
            content_length=extracted.content_length,
            truncated=extracted.truncated,
            full_output_path=extracted.full_output_path,
            page_type=None,
            schema=None,
            interactables=None,
            metadata={"extractor": "markdown", "format": fmt},
            warnings=list(extracted.warnings or []),
            page_map=None,
        )


__all__ = ["MarkdownExtractor"]
