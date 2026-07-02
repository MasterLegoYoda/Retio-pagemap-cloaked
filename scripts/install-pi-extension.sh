#!/usr/bin/env bash
# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only
#
# Install the PageMap Pi extension from this repo into
# ~/.pi/agent/extensions/pagemap/ as a symlink.
#
# What it does:
#   1. Runs `npm install` inside .pi/extensions/pagemap/ (pulls typebox).
#   2. Symlinks that directory into ~/.pi/agent/extensions/pagemap
#      so Pi's auto-discovery picks it up.
#   3. Verifies the extension is reachable by checking the linked
#      index.ts and printing the symlink target.
#
# Usage:
#   scripts/install-pi-extension.sh           # default target
#   scripts/install-pi-extension.sh --force   # replace an existing link
#
# Uninstall:
#   scripts/uninstall-pi-extension.sh         # removes the symlink only

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT_DIR="${REPO_ROOT}/.pi/extensions/pagemap"
EXT_ENTRY="${EXT_DIR}/index.ts"
GLOBAL_DIR="${HOME}/.pi/agent/extensions"
LINK_PATH="${GLOBAL_DIR}/pagemap"

force=0
for arg in "$@"; do
  case "$arg" in
    --force|-f) force=1 ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 64
      ;;
  esac
done

# Preflight.
for cmd in node npm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' is not on PATH. Install Node.js >= 18 and retry." >&2
    exit 1
  fi
done

if [[ ! -f "$EXT_ENTRY" ]]; then
  echo "Error: extension entry not found at $EXT_ENTRY" >&2
  exit 1
fi

mkdir -p "$GLOBAL_DIR"

# Replace an existing file/link if --force was passed (or if it's a
# stale regular file or broken symlink).
if [[ -e "$LINK_PATH" || -L "$LINK_PATH" ]]; then
  if [[ $force -eq 1 ]]; then
    rm -f "$LINK_PATH"
  else
    echo "Error: $LINK_PATH already exists." >&2
    echo "       Pass --force to replace it, or run scripts/uninstall-pi-extension.sh first." >&2
    exit 1
  fi
fi

# Pull typebox. Use --no-audit --no-fund to keep install quiet.
echo "[1/3] Installing extension dependencies (typebox)…"
(cd "$EXT_DIR" && npm install --no-audit --no-fund --loglevel=error)

# Symlink the whole extension directory so package.json and node_modules
# are reachable relative to index.ts.
echo "[2/3] Symlinking $LINK_PATH -> $EXT_DIR"
ln -s "$EXT_DIR" "$LINK_PATH"

# Verify and report.
echo "[3/3] Verifying…"
if [[ ! -e "$LINK_PATH/index.ts" ]]; then
  echo "Error: symlink created but $LINK_PATH/index.ts is not reachable." >&2
  exit 1
fi

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [[ "$node_major" -lt 18 ]]; then
  echo "Warning: Node $node_major detected; Pi extensions need Node >= 18." >&2
fi

cat <<EOF

Installed.
  Source:   $EXT_DIR
  Link:     $LINK_PATH
  Entry:    $LINK_PATH/index.ts

Next:
  - Restart Pi, or run /reload in the TUI.
  - The four tools pagemap_search, pagemap_fetch, pagemap_batch_fetch,
    and pagemap_sessions should appear alongside the built-ins.

Uninstall:
  scripts/uninstall-pi-extension.sh
EOF
