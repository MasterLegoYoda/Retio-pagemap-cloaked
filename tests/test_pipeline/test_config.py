# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for :mod:`pagemap.pipeline.config`.

Covers CLI > env > default resolution, typo detection, and the
special error path when ``pulpie`` is selected without the optional
dep.
"""

from __future__ import annotations

import pytest

from pagemap.pipeline.config import resolve_config


class TestResolveConfig:
    def setup_method(self):
        import os

        # Snapshot and clean the env.
        self._saved = {k: v for k, v in os.environ.items() if k.startswith("PAGEMAP_") and k not in {
            "PAGEMAP_RETRIEVER",
            "PAGEMAP_EXTRACTOR",
            "PAGEMAP_FAST_BACKEND",
            "PAGEMAP_SEARCH_PROVIDER",
            "PAGEMAP_FETCH_MODE",
        }}
        for k in [
            "PAGEMAP_RETRIEVER",
            "PAGEMAP_EXTRACTOR",
            "PAGEMAP_FAST_BACKEND",
            "PAGEMAP_SEARCH_PROVIDER",
            "PAGEMAP_FETCH_MODE",
        ]:
            os.environ.pop(k, None)

    def teardown_method(self):
        import os

        for k in [
            "PAGEMAP_RETRIEVER",
            "PAGEMAP_EXTRACTOR",
            "PAGEMAP_FAST_BACKEND",
            "PAGEMAP_SEARCH_PROVIDER",
            "PAGEMAP_FETCH_MODE",
        ]:
            os.environ.pop(k, None)
        for k, v in self._saved.items():
            os.environ[k] = v

    def test_defaults(self):
        cfg = resolve_config()
        assert cfg.retriever_name == "cloak"
        assert cfg.extractor_name == "retio"
        assert cfg.http_backend_name == "auto"
        assert cfg.search_provider_name == "duckduckgo"
        assert cfg.fetch_mode == "browser"

    def test_env_overrides(self):
        import os

        os.environ["PAGEMAP_RETRIEVER"] = "fetch"
        os.environ["PAGEMAP_EXTRACTOR"] = "markdown"
        os.environ["PAGEMAP_FAST_BACKEND"] = "urllib"
        os.environ["PAGEMAP_SEARCH_PROVIDER"] = "brave"
        os.environ["PAGEMAP_FETCH_MODE"] = "fast"

        cfg = resolve_config()
        assert cfg.retriever_name == "fetch"
        assert cfg.extractor_name == "markdown"
        assert cfg.http_backend_name == "urllib"
        assert cfg.search_provider_name == "brave"
        assert cfg.fetch_mode == "fast"

    def test_cli_overrides_env(self):
        import os

        os.environ["PAGEMAP_RETRIEVER"] = "fetch"
        os.environ["PAGEMAP_EXTRACTOR"] = "markdown"

        cfg = resolve_config(cli_retriever="cloak", cli_extractor="retio")
        assert cfg.retriever_name == "cloak"
        assert cfg.extractor_name == "retio"

    def test_auto_collapses_to_concrete_default(self):
        cfg = resolve_config(cli_retriever="auto", cli_extractor="auto")
        assert cfg.retriever_name == "cloak"
        assert cfg.extractor_name == "retio"

    def test_unknown_retriever_raises(self):
        with pytest.raises(ValueError) as exc:
            resolve_config(cli_retriever="nope")
        # The validation runs choice validation first, then existence.
        assert "nope" in str(exc.value)

    def test_unknown_extractor_raises(self):
        with pytest.raises(ValueError) as exc:
            resolve_config(cli_extractor="nope")
        assert "nope" in str(exc.value)

    def test_pulpie_without_dep_friendly_message(self):
        # We assume pulpie is not installed in CI.  If it IS installed
        # the resolve passes; the integration test will exercise the
        # full pipeline.  Skip when pulpie is available.
        import importlib.util

        if importlib.util.find_spec("pulpie") is not None:
            pytest.skip("pulpie is installed; happy path covered by integration test")
        with pytest.raises(ValueError) as exc:
            resolve_config(cli_extractor="pulpie")
        msg = str(exc.value)
        assert "pulpie" in msg
        assert "pip install" in msg

    def test_pipelineconfig_is_frozen(self):
        cfg = resolve_config()
        with pytest.raises((AttributeError, Exception)):
            cfg.retriever_name = "fetch"  # type: ignore[misc]
