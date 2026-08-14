"""Pulpie :class:`Extractor` — optional, markdown-only.

``pulpie`` is a third-party markdown extractor; the dep is installed
via ``pip install 'retio-pagemap[pulpie]'``.  When the package is
missing, :meth:`is_available` returns ``False`` and the registry
raises a clear error suggesting the install.

Pulpie returns main-content HTML/markdown without form-state
preservation or interactable extraction — so this extractor advertises
:attr:`Capability.MARKDOWN` only.  If a caller asks for
``INTERACTABLES`` / ``FORMS`` (e.g. ``get_page_map`` with
``--extractor pulpie``), the server raises
:class:`pagemap.pipeline.extractor.errors.MissingCapability`.
"""

from __future__ import annotations

import importlib.util
import logging
from typing import TYPE_CHECKING, Any

from .base import ExtractedDocument, ExtractorContext
from .capabilities import Capability
from .errors import ExtractorError

if TYPE_CHECKING:
    from pagemap.pipeline.retriever.base import FetchedDocument

logger = logging.getLogger(__name__)

_PULPIE_MODULE = "pulpie"


def _pulpie_available() -> bool:
    """Return ``True`` iff the ``pulpie`` package is importable."""
    return importlib.util.find_spec(_PULPIE_MODULE) is not None


class PulpieExtractor:
    """Markdown-only simplifier backed by the ``pulpie`` package.

    Attributes:
        name: ``"pulpie"`` (canonical registry key).
        capabilities: :attr:`Capability.MARKDOWN` only.
    """

    name: str = "pulpie"
    capabilities: Capability = Capability.MARKDOWN

    def __init__(self) -> None:
        self._extractor: Any | None = None
        self._init_failed: bool = False

    def is_available(self) -> bool:
        """Return ``True`` iff ``pulpie`` is installed and importable."""
        return _pulpie_available()

    def _get_extractor(self) -> Any:
        """Return a cached :class:`pulpie.Extractor`, instantiating lazily."""
        if self._extractor is not None:
            return self._extractor
        if self._init_failed:
            raise ExtractorError(
                "pulpie is not installed. Run `pip install 'retio-pagemap[pulpie]'` to enable this extractor."
            )
        try:
            mod = __import__(_PULPIE_MODULE, fromlist=["Extractor"])
        except Exception as exc:  # nosec B110
            self._init_failed = True
            raise ExtractorError(
                f"Failed to import pulpie: {exc}. Run `pip install 'retio-pagemap[pulpie]'` to install."
            ) from exc
        cls = getattr(mod, "Extractor", None)
        if cls is None:
            self._init_failed = True
            raise ExtractorError(
                "pulpie is installed but does not expose an Extractor class. "
                "Make sure you're on pulpie>=0.0.2."
            )
        try:
            self._extractor = cls()
        except Exception as exc:  # nosec B110
            self._init_failed = True
            raise ExtractorError(f"Failed to construct pulpie.Extractor: {exc}") from exc
        return self._extractor

    async def extract(
        self,
        doc: FetchedDocument,
        ctx: ExtractorContext,
    ) -> ExtractedDocument:
        """Call :func:`pulpie.Extractor.extract` and return a markdown body.

        The call is synchronous inside pulpie, so we wrap it (no
        :func:`asyncio.to_thread` because the pulpie model runs on
        GPU and the GIL is irrelevant — but the call is fast enough
        to inline).
        """
        if not doc.raw_html:
            raise ExtractorError("No HTML payload to extract from.")

        extractor = self._get_extractor()

        fmt = (ctx.fmt or "markdown").lower()
        try:
            result = extractor.extract(doc.raw_html)
        except Exception as exc:
            raise ExtractorError(f"pulpie extraction failed: {exc}") from exc

        # The pulpie result exposes markdown / html / n_main / n_other.
        if fmt == "html" and getattr(result, "html", None):
            content: str = str(result.html)
        else:
            content = str(getattr(result, "markdown", "") or "")

        # Lightweight title heuristic.  Pulpie does not surface a
        # structured title field, so we fall back to the standard
        # <title> tag (works for most pages).
        title = _extract_title(doc.raw_html)

        # Truncation: pulpie returns the kept-block content so it's
        # usually much smaller than the source HTML, but we still
        # honour ``max_chars`` to keep MCP responses bounded.
        max_chars = int(ctx.max_chars or 0)
        truncated = False
        full_output_path: str | None = None
        if max_chars > 0 and len(content) > max_chars:
            truncated = True
            head = content[:max_chars]
            full_output_path = None  # spillover is handled by the caller
            content = head

        metadata: dict[str, Any] = {
            "extractor": "pulpie",
            "n_main": int(getattr(result, "n_main", 0) or 0),
            "n_other": int(getattr(result, "n_other", 0) or 0),
            "format": fmt,
        }

        warnings: list[str] = []
        if fmt not in ("markdown", "html", "text", "json"):
            warnings.append(
                f"pulpie does not natively support format='{fmt}'; falling back to markdown."
            )

        return ExtractedDocument(
            title=title,
            content=content,
            content_length=len(content),
            truncated=truncated,
            full_output_path=full_output_path,
            page_type=None,
            schema=None,
            interactables=None,
            metadata=metadata,
            warnings=warnings,
            page_map=None,
        )


def _extract_title(raw_html: str) -> str | None:
    """Return the ``<title>`` text from ``raw_html``, or ``None``."""
    if not raw_html:
        return None
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "lxml")
        if soup.title and soup.title.string:
            return str(soup.title.string).strip()
    except Exception:  # nosec B110
        return None
    return None


__all__ = ["PulpieExtractor"]
