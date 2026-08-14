#!/usr/bin/env bash
# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only
#
# Install the PageMap Pi package from this repo into Pi's package registry.
#
# What it does:
#   1. Runs `npm install` inside pagemap-pi/ (pulls typebox, pi-coding-agent).
#   2. Installs the package into Pi via `pi install` (global or project-local).
#   3. Verifies the package is reachable by checking pi's package list.
#
# Usage:
#   scripts/install-pi-package.sh           # global install (~/.pi/agent/settings.json)
#   scripts/install-pi-package.sh -l|--project  # project install (.pi/settings.json)
#   scripts/install-pi-package.sh --force   # reinstall if already present
#
# Uninstall:
#   scripts/uninstall-pi-package.sh [-l]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_DIR="${REPO_ROOT}/pagemap-pi"
PKG_ENTRY="${PKG_DIR}/package.json"
GLOBAL_DIR="${HOME}/.pi/agent"

scope="global"
force=0

for arg in "$@"; do
  case "$arg" in
    -l|--local|--project)
      scope="project"
      ;;
    --force|-f)
      force=1
      ;;
    -h|--help)
      sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 64
      ;;
  esac
done

# Preflight.
for cmd in node npm pi; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' is not on PATH." >&2
    [[ "$cmd" = "pi" ]] && echo "       Install Pi from https://pi.dev" >&2
    exit 1
  fi
done

if [[ ! -f "$PKG_ENTRY" ]]; then
  echo "Error: package.json not found at $PKG_ENTRY" >&2
  exit 1
fi

# Install npm deps inside the package (peer deps are provided by Pi at runtime,
# but we still need typebox for TypeScript compilation / type-checking).
echo "[1/3] Installing package dependencies (typebox, typescript)…"
(cd "$PKG_DIR" && npm install --no-audit --no-fund --loglevel=error)

# Install into Pi.
echo "[2/3] Installing Pi package…"
pi_args=("install" "./pagemap-pi")
if [[ "$scope" = "project" ]]; then
  pi_args+=("-l")
fi
if [[ $force -eq 1 ]]; then
  # pi install doesn't have --force; remove first if present.
  pi remove pagemap-pi-package ${scope} 2>/dev/null || true
fi
pi "${pi_args[@]}"

# Verify.
echo "[3/3] Verifying…"
if [[ "$scope" = "project" ]]; then
  pi list -l | grep -q pagemap-pi-package
else
  pi list | grep -q pagemap-pi-package
fi

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [[ "$node_major" -lt 18 ]]; then
  echo "Warning: Node $node_major detected; Pi extensions need Node >= 18." >&2
fi

cat <<EOF

Installed.
  Package:  pagemap-pi-package
  Scope:    $scope
  Source:   $PKG_DIR

Next:
  - Restart Pi, or run /reload in the TUI.
  - The four tools pagemap_search, pagemap_fetch, pagemap_batch_fetch,
    and pagemap_sessions should appear alongside the built-ins.
  - Skills "pagemap-web-fetch" and "pagemap-browse-page" are available.

Uninstall:
  scripts/uninstall-pi-package.sh ${scope/#global/ -l}
EOF