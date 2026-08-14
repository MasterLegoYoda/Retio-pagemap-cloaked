"""Auto-register all built-in retrievers, extractors, and named
pipelines on import.

This module is imported by :mod:`pagemap.pipeline` (as a side
effect) so that any consumer — server, tests, SDK — gets the
same default set without having to opt in.  Tests that mutate the
registries should call :func:`_register_builtins` again after
resetting them.
"""

from __future__ import annotations

from .extractor.markdown import MarkdownExtractor
from .extractor.pulpie import PulpieExtractor
from .extractor.registry import register_extractor
from .extractor.retio import RetioExtractor
from .registry import register_named_pair
from .retriever.browser import BrowserRetriever
from .retriever.httpfetch import HttpRetriever
from .retriever.registry import register_retriever


def _register_builtins() -> None:
    """Register the built-in retrievers, extractors, and the most
    useful named pipelines.

    Re-running this is safe: registrations replace the previous
    factory, and any pre-registered named pair is no-op.
    """
    # Retrievers.
    register_retriever("cloak", lambda: BrowserRetriever())
    register_retriever("fetch", lambda: HttpRetriever())

    # Extractors.
    register_extractor("retio", lambda: RetioExtractor())
    register_extractor("pulpie", lambda: PulpieExtractor())
    register_extractor("markdown", lambda: MarkdownExtractor())

    # Named pipelines.  Pairs are registered lazily so an unavailable
    # extractor (e.g. pulpie without the dep) doesn't break startup.
    register_named_pair("cloak", "retio")  # the `default` pipeline
    register_named_pair("cloak", "pulpie")
    register_named_pair("cloak", "markdown")
    register_named_pair("fetch", "retio")
    register_named_pair("fetch", "pulpie")
    register_named_pair("fetch", "markdown")


_register_builtins()


__all__ = ["_register_builtins"]
