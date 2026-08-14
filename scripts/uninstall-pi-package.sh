#!/usr/bin/env bash
# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only
#
# Remove the PageMap Pi package.
#
# What it does:
#   1. Unregisters the package via `pi remove pagemap-pi-package`.
#   2. Optionally cleans the package's node_modules/.
#
# Usage:
#   scripts/uninstall-pi-package.sh           # global uninstall
#   scripts/uninstall-pi-package.sh --project # project-local uninstall
#   scripts/uninstall-pi-package.sh --clean   # also remove node_modules/

set -euo pipefail

scope="global"
clean_deps=false

for arg in "$@"; do
  case "$arg" in
    --project|-l)
      scope="project"
      ;;
    --clean)
      clean_deps=true
      ;;
    -h|--help)
      sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 64
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_DIR="${REPO_ROOT}/pagemap-pi"

echo "Removing PageMap Pi package (scope: $scope)…"
pi_args=("remove" "pagemap-pi-package")
if [[ "$scope" = "project" ]]; then
  pi_args+=("-l")
fi
pi "${pi_args[@]}" 2>/dev/null || {
  echo "Package was not installed (or already removed)."
}

if [[ "$clean_deps" = true ]]; then
  echo "Cleaning node_modules/…"
  rm -rf "${PKG_DIR}/node_modules"
  rm -f "${PKG_DIR}/package-lock.json"
fi

echo "Done."