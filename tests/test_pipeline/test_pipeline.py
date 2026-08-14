# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for :mod:`pagemap.pipeline.retriever` and the pipeline glue.

Covers:

* The :class:`Retriever` protocol duck-typing.
* The retriever registry semantics.
* The :class:`Pipeline` glue: ``run``, ``capabilities``,
  ``require_capability``, ``MissingCapability`` on missing bits.
* Named-pipeline resolution, including ``"<retriever>-<extractor>"``
  short-hand.
"""

from __future__ import annotations

import pytest

from pagemap.pipeline.core import Pipeline
from pagemap.pipeline.extractor import (
    CAPABILITY_DESCRIPTIONS,
    Capability,
    ExtractedDocument,
    ExtractorContext,
)
from pagemap.pipeline.extractor.errors import MissingCapability
from pagemap.pipeline.extractor.registry import (
    get_extractor,
    list_extractors,
    register_extractor,
)
from pagemap.pipeline.registry import (
    get_pipeline,
    list_pipelines,
    register_named_pair,
    resolve_pipeline,
)
from pagemap.pipeline.retriever import (
    FetchContext,
    FetchedDocument,
)
from pagemap.pipeline.retriever.registry import (
    get_retriever,
    list_retrievers,
    register_retriever,
    resolve_retriever,
)

# ── Test fixtures ──────────────────────────────────────────────────


class _FakeRetriever:
    """A trivial retriever that always returns the same payload."""

    name: str = "fake"
    kind: str = "other"

    def __init__(self, body: str = "<html><body>hi</body></html>") -> None:
        self._body = body
        self.last_ctx: FetchContext | None = None
        self.call_count = 0

    def is_available(self) -> bool:
        return True

    async def fetch(self, url: str, *, ctx: FetchContext) -> FetchedDocument:
        self.call_count += 1
        self.last_ctx = ctx
        return FetchedDocument(
            raw_html=self._body,
            final_url=url,
            status=200,
        )


class _MarkdownOnlyExtractor:
    name: str = "fake-md"
    capabilities: Capability = Capability.MARKDOWN

    def __init__(self) -> None:
        self.last_doc: FetchedDocument | None = None
        self.last_ctx: ExtractorContext | None = None
        self.call_count = 0

    def is_available(self) -> bool:
        return True

    async def extract(
        self,
        doc: FetchedDocument,
        ctx: ExtractorContext,
    ) -> ExtractedDocument:
        self.call_count += 1
        self.last_doc = doc
        self.last_ctx = ctx
        return ExtractedDocument(
            title="fake",
            content="<md>" + doc.raw_html + "</md>",
            content_length=len(doc.raw_html) + 9,
            truncated=False,
            full_output_path=None,
        )


class _FullCapabilityExtractor:
    name: str = "fake-full"
    capabilities: Capability = (
        Capability.MARKDOWN
        | Capability.INTERACTABLES
        | Capability.FORMS
        | Capability.PAGE_TYPE
        | Capability.SCHEMA
    )

    def is_available(self) -> bool:
        return True

    async def extract(
        self,
        doc: FetchedDocument,
        ctx: ExtractorContext,
    ) -> ExtractedDocument:
        return ExtractedDocument(
            title="full",
            content="OK",
            content_length=2,
            truncated=False,
            full_output_path=None,
        )


# ── Retriever registry ─────────────────────────────────────────────


class TestRetrieverRegistry:
    def setup_method(self):
        from pagemap.pipeline.extractor.registry import _reset_for_tests as _reset_ext
        from pagemap.pipeline.retriever.registry import _reset_for_tests as _reset_ret

        _reset_ext()
        _reset_ret()
        from pagemap.pipeline._builtins import _register_builtins

        _register_builtins()

    def test_list_includes_builtins(self):
        names = list_retrievers()
        assert "cloak" in names
        assert "fetch" in names

    def test_register_custom_retriever(self):
        register_retriever("fake", lambda: _FakeRetriever())
        r = get_retriever("fake")
        assert isinstance(r, _FakeRetriever)
        assert r.name == "fake"

    def test_unknown_retriever_raises(self):
        from pagemap.pipeline.retriever.errors import RetrieverNotFound

        with pytest.raises(RetrieverNotFound):
            get_retriever("nope")

    def test_resolve_retriever_picks_first_available(self):
        r = resolve_retriever("auto")
        assert r.name in list_retrievers()


# ── Extractor registry ─────────────────────────────────────────────


class TestExtractorRegistry:
    def setup_method(self):
        from pagemap.pipeline.extractor.registry import _reset_for_tests as _reset_ext
        from pagemap.pipeline.retriever.registry import _reset_for_tests as _reset_ret

        _reset_ext()
        _reset_ret()
        from pagemap.pipeline._builtins import _register_builtins

        _register_builtins()

    def test_list_includes_builtins(self):
        names = list_extractors()
        assert "retio" in names
        assert "markdown" in names
        # "pulpie" is registered but may not be available without the dep.

    def test_register_custom_extractor(self):
        register_extractor("fake-md", lambda: _MarkdownOnlyExtractor())
        e = get_extractor("fake-md")
        assert isinstance(e, _MarkdownOnlyExtractor)
        assert e.capabilities == Capability.MARKDOWN


# ── Pipeline core ──────────────────────────────────────────────────


class TestPipeline:
    def setup_method(self):
        from pagemap.pipeline.extractor.registry import _reset_for_tests as _reset_ext
        from pagemap.pipeline.retriever.registry import _reset_for_tests as _reset_ret

        _reset_ext()
        _reset_ret()
        from pagemap.pipeline._builtins import _register_builtins

        _register_builtins()

    async def test_run_calls_both_halves_in_order(self):
        retriever = _FakeRetriever(body="<html>HELLO</html>")
        extractor = _MarkdownOnlyExtractor()
        pipeline = Pipeline(name="test", retriever=retriever, extractor=extractor)

        result = await pipeline.run("https://example.com")
        assert retriever.call_count == 1
        assert extractor.call_count == 1
        assert result.content == "<md><html>HELLO</html></md>"
        # Retriever ctx is threaded through; the fetch is for the URL.
        assert retriever.last_ctx is not None

    def test_capabilities_proxies_extractor(self):
        pipeline = Pipeline(
            name="x",
            retriever=_FakeRetriever(),
            extractor=_MarkdownOnlyExtractor(),
        )
        assert pipeline.capabilities == Capability.MARKDOWN

    def test_require_capability_passes_when_present(self):
        pipeline = Pipeline(
            name="x",
            retriever=_FakeRetriever(),
            extractor=_FullCapabilityExtractor(),
        )
        # Should not raise.
        pipeline.require_capability(Capability.INTERACTABLES)
        pipeline.require_capability(Capability.FORMS)

    def test_require_capability_raises_when_missing(self):
        pipeline = Pipeline(
            name="md-only",
            retriever=_FakeRetriever(),
            extractor=_MarkdownOnlyExtractor(),
        )
        with pytest.raises(MissingCapability) as exc:
            pipeline.require_capability(Capability.INTERACTABLES, tool="get_page_map")
        msg = str(exc.value)
        assert "INTERACTABLES" in msg
        assert "md-only" in msg
        assert "fake-md" in msg
        assert "get_page_map" in msg


# ── Named pipeline registry ────────────────────────────────────────


class TestPipelineRegistry:
    def setup_method(self):
        from pagemap.pipeline.extractor.registry import _reset_for_tests as _reset_ext
        from pagemap.pipeline.retriever.registry import _reset_for_tests as _reset_ret

        _reset_ext()
        _reset_ret()
        from pagemap.pipeline._builtins import _register_builtins

        _register_builtins()

    def test_list_includes_builtin_pairs(self):
        names = list_pipelines()
        for expected in (
            "cloak-retio",
            "cloak-pulpie",
            "cloak-markdown",
            "fetch-retio",
            "fetch-pulpie",
            "fetch-markdown",
        ):
            assert expected in names

    def test_get_pipeline_returns_instance(self):
        p = get_pipeline("cloak-retio")
        assert p.name == "cloak-retio"
        assert p.retriever.name == "cloak"
        assert p.extractor.name == "retio"

    def test_resolve_pipeline_pair_short_hand(self):
        p = resolve_pipeline("fetch-markdown")
        assert p.retriever.name == "fetch"
        assert p.extractor.name == "markdown"

    def test_resolve_pipeline_unknown_raises(self):
        from pagemap.pipeline.registry import PipelineNotFound

        with pytest.raises(PipelineNotFound):
            resolve_pipeline("does-not-exist")

    def test_register_named_pair_then_resolve(self):
        register_retriever("fake", lambda: _FakeRetriever())
        register_extractor("fake-md", lambda: _MarkdownOnlyExtractor())
        register_named_pair("fake", "fake-md")
        p = resolve_pipeline("fake-fake-md")
        assert p.retriever.name == "fake"
        assert p.extractor.name == "fake-md"


# ── Capability descriptions are present in the public surface ──────


class TestPublicSurface:
    def test_capability_descriptions_match_documented_matrix(self):
        """The asymmetry the user flagged: pulpie is markdown-only."""
        from pagemap.pipeline.extractor.markdown import MarkdownExtractor
        from pagemap.pipeline.extractor.pulpie import PulpieExtractor
        from pagemap.pipeline.extractor.retio import RetioExtractor

        for e_cls in (RetioExtractor, MarkdownExtractor, PulpieExtractor):
            e = e_cls()
            for bit in (
                Capability.MARKDOWN,
                Capability.INTERACTABLES,
                Capability.FORMS,
                Capability.PAGE_TYPE,
                Capability.SCHEMA,
            ):
                # Sanity: every declared bit has a description, and
                # markdown-only extractors really do NOT advertise
                # interactables.
                desc = CAPABILITY_DESCRIPTIONS[int(bit)]
                assert desc
        # Markdown / pulpie should NOT advertise INTERACTABLES.
        for e_cls in (MarkdownExtractor, PulpieExtractor):
            e = e_cls()
            assert Capability.INTERACTABLES not in e.capabilities
        # Retio SHOULD advertise INTERACTABLES.
        retio = RetioExtractor()
        assert Capability.INTERACTABLES in retio.capabilities
