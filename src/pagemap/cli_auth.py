# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""CLI authentication — API key management for PageMap cloud.

Implements ``pagemap auth login/logout/status`` commands.
Login opens the dashboard to create an API key, then the user
pastes it into the CLI prompt.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)

CREDENTIALS_DIR = Path.home() / ".pagemap"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"

_DASHBOARD_URL = "https://retio.ai/dashboard/keys"


# ── Credential storage ───────────────────────────────────────────────


def load_credentials() -> dict | None:
    """Load credentials from ~/.pagemap/credentials.json, or None."""
    if not CREDENTIALS_FILE.exists():
        return None
    try:
        return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_credentials(creds: dict) -> None:
    """Save credentials to ~/.pagemap/credentials.json with 0600 perms."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(CREDENTIALS_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (json.dumps(creds, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def _delete_credentials() -> bool:
    """Delete credentials file. Returns True if file existed."""
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
        return True
    return False


def get_api_key() -> str | None:
    """Return stored API key, or None. Used by other CLI commands."""
    creds = load_credentials()
    if creds:
        return creds.get("api_key")
    return os.environ.get("PAGEMAP_API_KEY")


# ── Commands ─────────────────────────────────────────────────────────


def login() -> None:
    """Open dashboard to create API key, then save it locally."""
    existing = load_credentials()
    if existing and existing.get("api_key"):
        print(f"Already logged in (key: {existing['api_key'][:16]}...)")
        print("Run 'pagemap auth logout' first to re-authenticate.")
        return

    print(f"Opening {_DASHBOARD_URL}")
    print("1. Log in with GitHub or Google")
    print("2. Click 'Create API Key'")
    print("3. Copy the key and paste it below")
    print()
    webbrowser.open(_DASHBOARD_URL)

    try:
        api_key = input("Paste your API key: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(130)

    if not api_key:
        print("Error: No key provided.", file=sys.stderr)
        sys.exit(1)

    if not api_key.startswith("sk-pm-"):
        print("Error: Invalid key format. Keys start with 'sk-pm-'.", file=sys.stderr)
        sys.exit(1)

    _save_credentials(
        {
            "api_key": api_key,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )

    print(f"API key saved to {CREDENTIALS_FILE}")


def logout() -> None:
    """Remove stored credentials."""
    if _delete_credentials():
        print("Logged out. Credentials removed.")
    else:
        print("No credentials found.")


def status() -> None:
    """Show current authentication status."""
    creds = load_credentials()
    if not creds:
        env_key = os.environ.get("PAGEMAP_API_KEY", "")
        if env_key:
            print(f"API key: {env_key[:16]}...{env_key[-4:]} (from PAGEMAP_API_KEY env)")
        else:
            print("Not logged in. Run: pagemap auth login")
        return

    api_key = creds.get("api_key", "")
    created = creds.get("created_at", "unknown")
    print(f"API key: {api_key[:16]}...{api_key[-4:]}")
    print(f"Login date: {created}")
    print(f"Credentials: {CREDENTIALS_FILE}")
