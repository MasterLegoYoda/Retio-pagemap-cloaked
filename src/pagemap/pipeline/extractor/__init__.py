"""Extractors — pluggable content transformers that turn a :class:`FetchedDocument` into a :class:`ExtractedDocument`.

The built-in extractors are:

* :class:`RetioExtractor` (``name="retio"``) — the existing PageMap
  core, declares all five capabilities.
* :class:`PulpieExtractor` (``name="pulpie"``) — uses the
  ``pulpie`` encoder model; declares :attr:`Capability.MARKDOWN`
  only.  Opt-in via ``pip install 'retio-pagemap[pulpie]'``.
* :class:`MarkdownExtractor` (``name="markdown"``) — the cheap
  BeautifulSoup path, declares :attr:`Capability.MARKDOWN` only.

All three register themselves on import via
:mod:`pagemap.pipeline._builtins`.  See :func:`register_extractor`
for the extension point.
"""

from __future__ import annotations

from .base import ExtractedDocument, Extractor, ExtractorContext
from .capabilities import (
    CAPABILITY_DESCRIPTIONS,
    CAPABILITY_NAMES,
    Capability,
    capability_description,
    capability_name,
)
from .errors import ExtractorError, ExtractorNotFound, MissingCapability
from .markdown import MarkdownExtractor
from .pulpie import PulpieExtractor
from .registry import (
    _reset_for_tests,
    get_extractor,
    list_extractors,
    register_extractor,
    resolve_extractor,
)
from .retio import RetioExtractor

__all__ = [
    "CAPABILITY_DESCRIPTIONS",
    "CAPABILITY_NAMES",
    "Capability",
    "ExtractedDocument",
    "Extractor",
    "ExtractorContext",
    "ExtractorError",
    "ExtractorNotFound",
    "MarkdownExtractor",
    "MissingCapability",
    "PulpieExtractor",
    "RetioExtractor",
    "_reset_for_tests",
    "capability_description",
    "capability_name",
    "get_extractor",
    "list_extractors",
    "register_extractor",
    "resolve_extractor",
]
