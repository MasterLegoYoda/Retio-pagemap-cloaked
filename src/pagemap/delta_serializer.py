# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Backward-compat shim: import from pagemap.core.delta_serializer instead."""

from pagemap.core.delta_serializer import (  # noqa: F401
    DELTA_PACKET_SCHEMA_VERSION,
    DELTA_SERIALIZER_NAME,
    DELTA_SERIALIZER_VERSION,
    to_delta_json,
    to_delta_packet,
)

__all__ = [
    "DELTA_PACKET_SCHEMA_VERSION",
    "DELTA_SERIALIZER_NAME",
    "DELTA_SERIALIZER_VERSION",
    "to_delta_json",
    "to_delta_packet",
]
