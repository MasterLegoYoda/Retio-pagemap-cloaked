# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Smoke tests for the Pi package contract.

The package bundles an extension and skills. We assert:
- package.json has pi-package keyword and correct pi.* manifest
- extension index.ts is loadable, registers 4 tools with new params
- skills directory contains SKILL.md files
- CLI subcommands the extension shells out to exist
- install scripts are present and executable
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = REPO_ROOT / "pagemap-pi"
EXT_DIR = PKG_ROOT / "extensions" / "pagemap"
SKILLS_DIR = PKG_ROOT / "skills"
INDEX_TS = EXT_DIR / "index.ts"
PACKAGE_JSON = PKG_ROOT / "package.json"
EXT_PACKAGE_JSON = EXT_DIR / "package.json"

INSTALL = REPO_ROOT / "scripts" / "install-pi-package.sh"
UNINSTALL = REPO_ROOT / "scripts" / "uninstall-pi-package.sh"


class TestPackageManifest:
    def test_package_json_exists(self):
        assert PACKAGE_JSON.is_file(), f"missing {PACKAGE_JSON}"

    def test_package_json_well_formed(self):
        data = json.loads(PACKAGE_JSON.read_text())
        assert data["name"] == "pagemap-pi-package"
        assert "pi-package" in data.get("keywords", [])
        assert "pi" in data
        assert data["pi"]["extensions"] == ["./extensions/pagemap"]
        assert data["pi"]["skills"] == ["./skills"]

    def test_package_json_has_peer_deps(self):
        data = json.loads(PACKAGE_JSON.read_text())
        peer = data.get("peerDependencies", {})
        assert "@earendil-works/pi-coding-agent" in peer
        assert "typebox" in peer


class TestExtensionFiles:
    def test_index_ts_exists(self):
        assert INDEX_TS.is_file(), f"missing {INDEX_TS}"

    def test_ext_package_json_exists(self):
        assert EXT_PACKAGE_JSON.is_file(), f"missing {EXT_PACKAGE_JSON}"

    def test_ext_package_json_well_formed(self):
        data = json.loads(EXT_PACKAGE_JSON.read_text())
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
        assert "from \"mcp\"" not in text
        assert "require(\"mcp\"" not in text
        assert "from 'mcp'" not in text
        assert "zod" not in text.lower(), "use typebox, not zod"

    def test_ext_package_json_no_mcp_dep(self):
        data = json.loads(EXT_PACKAGE_JSON.read_text())
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        assert "mcp" not in deps, "extension must not depend on MCP"
        assert "zod" not in deps

    def test_search_params_has_new_fields(self):
        text = INDEX_TS.read_text()
        # SearchParams should have provider, domain, use_browser
        assert "provider" in text
        assert "domain" in text
        assert "use_browser" in text
        # Enum values for provider
        for p in ("duckduckgo", "brave", "bing", "google", "searxng", "exa", "tavily", "firecrawl"):
            assert f'"{p}"' in text

    def test_fetch_params_has_mode(self):
        text = INDEX_TS.read_text()
        # FetchParams and BatchFetchParams should have mode property
        assert "mode:" in text
        assert '"browser"' in text or "'browser'" in text
        assert '"fast"' in text or "'fast'" in text

    def test_timeout_bumped_to_120s(self):
        text = INDEX_TS.read_text()
        assert "120_000" in text or "120000" in text


class TestSkillsDir:
    def test_skills_dir_exists(self):
        assert SKILLS_DIR.is_dir(), f"missing {SKILLS_DIR}"

    def test_web_fetch_skill(self):
        skill = SKILLS_DIR / "pagemap-web-fetch" / "SKILL.md"
        assert skill.is_file(), f"missing {skill}"
        text = skill.read_text()
        assert "name: pagemap-web-fetch" in text
        assert "pagemap_search" in text
        assert "pagemap_fetch" in text
        assert "pagemap_batch_fetch" in text
        assert "pagemap_sessions" in text

    def test_browse_page_skill(self):
        skill = SKILLS_DIR / "pagemap-browse-page" / "SKILL.md"
        assert skill.is_file(), f"missing {skill}"
        text = skill.read_text()
        assert "name: pagemap-browse-page" in text
        assert "get_page_map" in text
        assert "execute_action" in text


class TestLocalhostDetection:
    """The extension sets PAGEMAP_ALLOW_LOCAL=1 for localhost URLs."""

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
    """The extension shells out to specific pagemap subcommands."""

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
    """The install / uninstall scripts are the documented entry points."""

    def test_install_script_exists(self):
        assert INSTALL.is_file()

    def test_uninstall_script_exists(self):
        assert UNINSTALL.is_file()

    def test_install_script_executable(self):
        import stat

        mode = INSTALL.stat().st_mode
        assert mode & stat.S_IXUSR, "install-pi-package.sh must be executable"

    def test_uninstall_script_executable(self):
        import stat

        mode = UNINSTALL.stat().st_mode
        assert mode & stat.S_IXUSR, "uninstall-pi-package.sh must be executable"

    def test_install_script_uses_npm_and_pi_install(self):
        text = INSTALL.read_text()
        assert "npm install" in text
        assert "pi install" in text
        assert "pagemap-pi" in text

    def test_uninstall_script_uses_pi_remove(self):
        text = UNINSTALL.read_text()
        assert "pi remove" in text
        assert "pagemap-pi" in text

    def test_install_script_help(self, capsys):
        import subprocess

        result = subprocess.run(
            ["bash", str(INSTALL), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Usage:" in result.stdout
        assert "--force" in result.stdout
        assert "--project" in result.stdout
