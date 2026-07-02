# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for the web-fetch / sessions CLI subcommands."""

from __future__ import annotations

import argparse
import sys
from unittest.mock import patch

import pytest

from pagemap.cli import main


def _parse(argv: list[str]) -> argparse.Namespace:
    """Run the CLI parser and return the namespace."""
    with pytest.raises(SystemExit) as exc_info, patch.object(sys, "argv", ["pagemap", *argv]):
        main()
    assert exc_info.value.code == 0


class TestSearchParser:
    def test_search_help(self):
        # Should not raise; we just need the parser to accept the args.
        _parse(["search", "--help"])

    def test_search_default_provider(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(sys, "argv", ["pagemap", "search", "hello world", "--max-results", "5"]),
            patch("pagemap.cli.cmd_search", _capture),
        ):
            main()
        ns = called["args"]
        assert ns.query == "hello world"
        assert ns.max_results == 5
        assert ns.provider == "duckduckgo"
        assert ns.session is None
        assert ns.format == "markdown"

    def test_search_new_session(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(
                sys,
                "argv",
                ["pagemap", "search", "x", "--session", "new:docs"],
            ),
            patch("pagemap.cli.cmd_search", _capture),
        ):
            main()
        assert called["args"].session == "new:docs"

    def test_search_provider_override(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(sys, "argv", ["pagemap", "search", "x", "--provider", "brave"]),
            patch("pagemap.cli.cmd_search", _capture),
        ):
            main()
        assert called["args"].provider == "brave"


class TestFetchParser:
    def test_fetch_help(self):
        _parse(["fetch", "--help"])

    def test_fetch_defaults(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(sys, "argv", ["pagemap", "fetch", "https://example.com"]),
            patch("pagemap.cli.cmd_fetch", _capture),
        ):
            main()
        ns = called["args"]
        assert ns.url == "https://example.com"
        assert ns.mode == "browser"
        assert ns.format == "markdown"
        assert ns.max_chars == 50_000
        assert ns.session is None

    def test_fetch_format_and_session(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(
                sys,
                "argv",
                [
                    "pagemap",
                    "fetch",
                    "https://example.com",
                    "--format",
                    "text",
                    "--session",
                    "new:docs",
                    "--max-chars",
                    "1000",
                ],
            ),
            patch("pagemap.cli.cmd_fetch", _capture),
        ):
            main()
        ns = called["args"]
        assert ns.format == "text"
        assert ns.session == "new:docs"
        assert ns.max_chars == 1000


class TestBatchFetchParser:
    def test_batch_fetch_help(self):
        _parse(["batch-fetch", "--help"])

    def test_batch_fetch_urls(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(
                sys,
                "argv",
                [
                    "pagemap",
                    "batch-fetch",
                    "https://a.example",
                    "https://b.example",
                    "--max-concurrency",
                    "3",
                ],
            ),
            patch("pagemap.cli.cmd_batch_fetch", _capture),
        ):
            main()
        ns = called["args"]
        assert ns.urls == ["https://a.example", "https://b.example"]
        assert ns.max_concurrency == 3


class TestSessionsParser:
    def test_sessions_help(self):
        _parse(["sessions", "--help"])

    def test_sessions_list(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(sys, "argv", ["pagemap", "sessions", "list"]),
            patch("pagemap.cli.cmd_sessions", _capture),
        ):
            main()
        assert called["args"].sessions_command == "list"

    def test_sessions_close_default(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(sys, "argv", ["pagemap", "sessions", "close"]),
            patch("pagemap.cli.cmd_sessions", _capture),
        ):
            main()
        # default: reset the default session
        assert called["args"].sessions_command == "close"
        assert called["args"].session_id == "default"

    def test_sessions_close_named(self):
        called = {}

        def _capture(args):
            called["args"] = args

        with (
            patch.object(
                sys,
                "argv",
                ["pagemap", "sessions", "close", "docs"],
            ),
            patch("pagemap.cli.cmd_sessions", _capture),
        ):
            main()
        assert called["args"].session_id == "docs"
