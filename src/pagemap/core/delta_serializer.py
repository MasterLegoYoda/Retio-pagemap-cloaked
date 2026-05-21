# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Delta Intelligence serializer for PageMap.

This module keeps the public PageMap JSON and agent-prompt formats stable while
adding an evidence-packet output that is easier for Delta Native / DeltaDB to
consume.  The packet is digest-bound, authority-neutral, and focused on
claim/evidence/provenance surfaces rather than direct agent instructions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any

from . import Interactable, PageMap
from .sanitizer import sanitize_text

DELTA_PACKET_SCHEMA_VERSION = "PAGEMAP_DELTA_INTELLIGENCE_PACKET_v1"
DELTA_SERIALIZER_NAME = "pagemap_delta_serializer"
DELTA_SERIALIZER_VERSION = "1.0.0"
_MAX_TEXT_CHARS = 640
_MAX_CONTEXT_LINES = 24
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_LABEL_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_.-]{1,48})\b")
_ASSERTION_RE = re.compile(r"\b(?:Assertion|Asserted|Theorem|Axiom|Definition|Lemma|Rule)\b", re.IGNORECASE)
_FORMAL_MARKER_RE = re.compile(r"(\|-|⊢|=>|->|<->|∀|∃|=)")


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(data: Any) -> str:
    return hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()


def _bounded_text(value: str, *, max_chars: int = _MAX_TEXT_CHARS) -> str:
    text = sanitize_text(str(value or ""), max_len=max_chars).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _valid_digest(value: str) -> bool:
    return bool(_DIGEST_RE.fullmatch(value))


def _unit(
    *,
    unit_kind: str,
    source_field: str,
    text: str,
    source_index: int,
    role: str = "evidence",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    excerpt = _bounded_text(text)
    payload = {
        "unit_kind": unit_kind,
        "source_field": source_field,
        "source_index": source_index,
        "text_excerpt": excerpt,
        "text_digest": _digest({"text": excerpt}),
        "role": role,
        **(extra or {}),
    }
    unit_digest = _digest(payload)
    return {
        "unit_id": f"pmdu_{unit_digest[:16]}",
        "record_kind": "pagemap_delta_evidence_unit",
        "unit_digest": unit_digest,
        **payload,
    }


def _interactable_unit(item: Interactable, source_index: int) -> dict[str, Any]:
    text = f"{item.role}: {item.name} ({item.affordance})"
    return _unit(
        unit_kind="interaction_ref",
        source_field="interactables",
        source_index=source_index,
        text=text,
        role="action_surface",
        extra={
            "ref": item.ref,
            "interaction_role": item.role,
            "affordance": item.affordance,
            "region": item.region,
            "tier": item.tier,
            "name_source": item.name_source,
        },
    )


def _context_units(page_map: PageMap) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    if page_map.title:
        units.append(
            _unit(
                unit_kind="title",
                source_field="title",
                source_index=0,
                text=page_map.title,
                role="identity",
            )
        )
    for index, line in enumerate(page_map.pruned_context.splitlines()[:_MAX_CONTEXT_LINES]):
        clean = line.strip()
        if not clean:
            continue
        kind = _context_unit_kind(clean)
        units.append(
            _unit(
                unit_kind=kind,
                source_field="pruned_context",
                source_index=index,
                text=clean,
                role="evidence",
            )
        )
    return units


def _metadata_units(page_map: PageMap) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for index, key in enumerate(sorted(page_map.metadata.keys())):
        if key.startswith("_"):
            continue
        value = page_map.metadata[key]
        if isinstance(value, (dict, list, tuple, set)):
            text = json.dumps(value, sort_keys=True, ensure_ascii=True)
        else:
            text = str(value)
        if not text.strip():
            continue
        units.append(
            _unit(
                unit_kind="metadata_field",
                source_field=f"metadata.{key}",
                source_index=index,
                text=f"{key}: {text}",
                role="structured_metadata",
            )
        )
    return units


def _context_unit_kind(line: str) -> str:
    lowered = line.lower()
    if "proof of theorem" in lowered or "proof" in lowered:
        return "proof_marker"
    if "definition" in lowered or lowered.startswith("df-"):
        return "definition_surface"
    if "axiom" in lowered or lowered.startswith("ax-"):
        return "axiom_surface"
    if "assertion" in lowered or _FORMAL_MARKER_RE.search(line):
        return "statement_surface"
    if line.startswith("#") or len(line.split()) <= 8:
        return "heading_or_label"
    return "content_surface"


def _candidate_kind(label: str, evidence_text: str) -> str:
    lowered = evidence_text.lower()
    if "proof of theorem" in lowered or "theorem" in lowered:
        return "theorem_candidate"
    if label.startswith("ax-") or "axiom" in lowered or "rule of" in lowered:
        return "axiom_or_inference_rule_candidate"
    if label.startswith("df-") or "definition" in lowered:
        return "definition_candidate"
    if _FORMAL_MARKER_RE.search(evidence_text):
        return "formal_statement_candidate"
    return "claim_candidate"


def _extract_label(text: str, fallback: str) -> str:
    if fallback:
        fallback_label = fallback.strip().split()[0]
        if fallback_label:
            return fallback_label[:80]
    match = _LABEL_RE.search(text)
    return match.group(1)[:80] if match else "claim"


def _claim_candidates(units: list[dict[str, Any]], page_map: PageMap) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    title_label = _extract_label(page_map.title, "")
    for unit in units:
        text = str(unit.get("text_excerpt", ""))
        unit_kind = str(unit.get("unit_kind", ""))
        if unit_kind not in {
            "statement_surface",
            "proof_marker",
            "definition_surface",
            "axiom_surface",
            "heading_or_label",
        } and not _ASSERTION_RE.search(text):
            continue
        label = _extract_label(text, title_label)
        payload = {
            "label": label,
            "candidate_kind": _candidate_kind(label, text),
            "statement_hint": _bounded_text(text),
            "supporting_unit_ids": (unit["unit_id"],),
            "source_uri": page_map.url,
            "truth_claim_opened": False,
            "native_adoption_opened": False,
            "deltadb_write_opened": False,
        }
        candidate_digest = _digest(payload)
        candidates.append(
            {
                "candidate_id": f"pmdc_{candidate_digest[:16]}",
                "record_kind": "pagemap_delta_claim_candidate",
                "candidate_digest": candidate_digest,
                **payload,
            }
        )
    seen: set[str] = set()
    deduped = []
    for candidate in candidates:
        key = str(candidate["candidate_digest"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _authority() -> dict[str, bool]:
    return {
        "pagemap_output_materialized": True,
        "raw_body_retained": False,
        "response_body_stored": False,
        "truth_claim_opened": False,
        "native_adoption_opened": False,
        "deltadb_write_opened": False,
        "scheduler_authority_opened": False,
        "external_write_opened": False,
        "private_repo_write_opened": False,
    }


def to_delta_packet(
    page_map: PageMap,
    *,
    source_run_id: str = "",
    source_observation_digest: str = "",
) -> dict[str, Any]:
    """Serialize a PageMap into a Delta Intelligence evidence packet.

    The packet is intentionally authority-neutral.  It is suitable for DeltaDB
    candidate memory and follow-on native review, not direct truth/adoption.
    """

    if source_observation_digest and not _valid_digest(source_observation_digest):
        raise ValueError("source_observation_digest must be a lowercase 64-char sha256 digest")
    evidence_units = [
        *_context_units(page_map),
        *_metadata_units(page_map),
        *(_interactable_unit(item, index) for index, item in enumerate(page_map.interactables)),
    ]
    content_digest = _digest(
        {
            "url": page_map.url,
            "title": page_map.title,
            "page_type": page_map.page_type,
            "pruned_context": page_map.pruned_context,
            "metadata": page_map.metadata,
            "images": page_map.images,
            "interactables": [asdict(item) for item in page_map.interactables],
        }
    )
    evidence_digest = _digest(tuple(unit["unit_digest"] for unit in evidence_units))
    candidates = _claim_candidates(evidence_units, page_map)
    provenance = {
        "serializer_name": DELTA_SERIALIZER_NAME,
        "serializer_version": DELTA_SERIALIZER_VERSION,
        "source_run_id": source_run_id,
        "source_observation_digest": source_observation_digest,
        "pruned_tokens": page_map.pruned_tokens,
        "interactable_count": page_map.total_interactables,
        "image_count": len(page_map.images),
        "warning_count": len(page_map.warnings),
        "navigation_hint_count": len(page_map.navigation_hints),
        "metadata_digest": _digest(page_map.metadata),
    }
    packet_payload = {
        "schema_version": DELTA_PACKET_SCHEMA_VERSION,
        "source_uri": page_map.url,
        "title": page_map.title,
        "page_type": page_map.page_type,
        "content_digest": content_digest,
        "evidence_digest": evidence_digest,
        "claim_candidate_digests": tuple(candidate["candidate_digest"] for candidate in candidates),
        "authority": _authority(),
        "provenance": provenance,
    }
    packet_digest = _digest(packet_payload)
    return {
        "packet_id": f"pmdelta_{packet_digest[:16]}",
        "record_kind": "pagemap_delta_intelligence_packet",
        "packet_digest": packet_digest,
        **packet_payload,
        "evidence_units": evidence_units,
        "claim_candidates": candidates,
    }


def to_delta_json(page_map: PageMap, *, indent: int = 2, **kwargs: Any) -> str:
    """Serialize a PageMap Delta packet to JSON."""

    return json.dumps(to_delta_packet(page_map, **kwargs), ensure_ascii=False, indent=indent)


__all__ = [
    "DELTA_PACKET_SCHEMA_VERSION",
    "DELTA_SERIALIZER_NAME",
    "DELTA_SERIALIZER_VERSION",
    "to_delta_json",
    "to_delta_packet",
]
