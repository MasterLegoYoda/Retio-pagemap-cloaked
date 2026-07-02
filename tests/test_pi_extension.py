# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Smoke tests for the Pi extension contract.

The extension itself is TypeScript and runs inside Node + Pi, so we
don't try to execute it from Python. Instead we assert the
contract that lets the extension work: the package.json is well-formed,
the entry point is loadable as text, the four tool names are present,
and the CLI subcommands the extension shells out to exist.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXT_DIR = REPO_ROOT / ".pi" / "extensions" / "pagemap"
INDEX_TS = EXT_DIR / "index.ts"
PACKAGE_JSON = EXT_DIR / "package.json"


class TestExtensionFiles:
    def test_index_ts_exists(self):
        assert INDEX_TS.is_file(), f"missing {INDEX_TS}"

    def test_package_json_exists(self):
        assert PACKAGE_JSON.is_file(), f"missing {PACKAGE_JSON}"

    def test_package_json_well_formed(self):
        data = json.loads(PACKAGE_JSON.read_text())
        assert data["name"] == "pagemap-pi-extension"
        assert "typebox" in data.get("dependencies", {})
        assert data.get("pi", {}).get("extensions") == ["./index.ts"]

    def test_index_uses_typebox(self):
        text = INDEX_TS.read_text()
        assert "from \"typebox\"" in text
        assert "Type.Object" in text
        assert "Type.String" in text
        assert "Type.Number" in text
        assert "Type.Optional" in text
        assert "Type.Union" in text

    def test_index_registers_four_tools(self):
        text = INDEX_TS.read_text()
        for tool in ("pagemap_search", "pagemap_fetch", "pagemap_batch_fetch", "pagemap_sessions"):
            assert f'name: "{tool}"' in text, f"tool {tool!r} not registered"

    def test_index_uses_extension_api(self):
        text = INDEX_TS.read_text()
        assert "ExtensionAPI" in text
        assert "pi.registerTool" in text
        assert "default function" in text

    def test_index_no_mcp_or_zod(self):
        text = INDEX_TS.read_text()
        # Disallow the MCP SDK as an import / require target.
        assert "from \"mcp\"" not in text
        assert "require(\"mcp\"" not in text
        assert "from 'mcp'" not in text
        assert "zod" not in text.lower(), "use typebox, not zod"

    def test_package_json_no_mcp_dep(self):
        data = json.loads(PACKAGE_JSON.read_text())
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        assert "mcp" not in deps, "extension must not depend on MCP"
        assert "zod" not in deps


class TestLocalhostDetection:
    """The extension sets PAGEMAP_ALLOW_LOCAL=1 for localhost URLs. The
    regex lives in index.ts; we re-implement the same predicate in
    Python here so we can lock down its behavior in tests without
    spinning up Node."""

    LOCALHOST_RE = re.compile(
        r"^(?:[a-z][a-z0-9+.-]*://)?(?:localhost|127\.0\.0\.1|\[::1\]|::1)(?::\d+)?(?:/|$)",
        re.IGNORECASE,
    )

    def is_local(self, url: str) -> bool:
        return bool(self.LOCALHOST_RE.match(url))

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:8000/docs",
            "http://localhost/foo",
            "https://127.0.0.1:3000/api",
            "http://127.0.0.1",
            "http://[::1]:8080/x",
            "https://[::1]/",
        ],
    )
    def test_localhost_matches(self, url: str):
        assert self.is_local(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com",
            "https://docs.example.com/localhost.evil.com",
            "https://127.0.0.1.evil.com",
        ],
    )
    def test_non_local_does_not_match(self, url: str):
        assert not self.is_local(url)


class TestExtensionSubcommands:
    """The extension shells out to specific pagemap subcommands. The
    Python CLI parser is the source of truth for the flag set, so we
    assert each subcommand the extension uses is registered."""

    def test_all_extension_subcommands_have_help(self, capsys):
        import sys

        from pagemap.cli import main

        for sub in ("search", "fetch", "batch-fetch", "sessions"):
            with (
                patch.object(sys, "argv", ["pagemap", sub, "--help"]),
                pytest.raises(SystemExit) as exc,
            ):
                main()
            assert exc.value.code == 0, f"{sub} --help exited non-zero"
        out = capsys.readouterr().out
        assert "search" in out
        assert "fetch" in out
        assert "batch-fetch" in out
        assert "sessions" in out


class TestInstallScripts:
    """The install / uninstall scripts and Makefile targets are the
    documented entry points. We assert they exist, are executable, and
    contain the right commands — without actually running npm install
    or creating the symlink in CI."""

    INSTALL = REPO_ROOT / "scripts" / "install-pi-extension.sh"
    UNINSTALL = REPO_ROOT / "scripts" / "uninstall-pi-extension.sh"
    MAKEFILE = REPO_ROOT / "Makefile"

    def test_install_script_exists(self):
        assert self.INSTALL.is_file()

    def test_uninstall_script_exists(self):
        assert self.UNINSTALL.is_file()

    def test_install_script_executable(self):
        import stat

        mode = self.INSTALL.stat().st_mode
        assert mode & stat.S_IXUSR, "install-pi-extension.sh must be executable"

    def test_uninstall_script_executable(self):
        import stat

        mode = self.UNINSTALL.stat().st_mode
        assert mode & stat.S_IXUSR, "uninstall-pi-extension.sh must be executable"

    def test_install_script_uses_npm_and_symlink(self):
        text = self.INSTALL.read_text()
        assert "npm install" in text
        assert "ln -s" in text
        assert ".pi/agent/extensions/pagemap" in text
        assert "--force" in text

    def test_uninstall_script_removes_symlink(self):
        text = self.UNINSTALL.read_text()
        assert "rm" in text
        assert ".pi/agent/extensions/pagemap" in text

    def test_makefile_has_targets(self):
        text = self.MAKEFILE.read_text()
        assert "pi-install:" in text
        assert "pi-uninstall:" in text
        assert "install-pi-extension.sh" in text

    def test_install_script_help(self, capsys):
        import subprocess

        result = subprocess.run(
            ["bash", str(self.INSTALL), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Usage:" in result.stdout
        assert "--force" in result.stdout
