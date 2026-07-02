#!/usr/bin/env bash
# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only
#
# Remove the PageMap Pi extension symlink from
# ~/.pi/agent/extensions/pagemap. Does not touch the source repo.

set -euo pipefail

LINK_PATH="${HOME}/.pi/agent/extensions/pagemap"

if [[ -L "$LINK_PATH" ]]; then
  rm "$LINK_PATH"
  echo "Removed $LINK_PATH"
elif [[ -e "$LINK_PATH" ]]; then
  echo "Error: $LINK_PATH exists but is not a symlink. Refusing to delete." >&2
  echo "       Inspect it manually and remove it yourself if you're sure." >&2
  exit 1
else
  echo "Nothing to do: $LINK_PATH does not exist."
fi
