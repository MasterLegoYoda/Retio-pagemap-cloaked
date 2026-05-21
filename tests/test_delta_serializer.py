# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for Delta Intelligence PageMap serializer."""

from __future__ import annotations

import json

import pytest

from pagemap import Interactable, PageMap
from pagemap.delta_serializer import (
    DELTA_PACKET_SCHEMA_VERSION,
    to_delta_json,
    to_delta_packet,
)


def _page_map() -> PageMap:
    return PageMap(
        url="https://us.metamath.org/mpeuni/ax-mp.html",
        title="ax-mp",
        page_type="documentation",
        interactables=[
            Interactable(
                ref=1,
                role="link",
                name="breq1",
                affordance="click",
                region="main",
                tier=2,
                name_source="contents",
            )
        ],
        pruned_context=(
            "ax-mp\n"
            "Description: Rule of Modus Ponens.\n"
            "Assertion Ref Expression ax-mp |- ( ph -> ps )\n"
            "Proof of Theorem ax-mp"
        ),
        pruned_tokens=28,
        generation_ms=12.3,
        metadata={"name": "ax-mp", "_total_budget": 5000},
    )


def test_delta_packet_is_digest_bound_and_authority_neutral() -> None:
    packet = to_delta_packet(
        _page_map(),
        source_run_id="usrcx_fixture",
        source_observation_digest="a" * 64,
    )

    assert packet["record_kind"] == "pagemap_delta_intelligence_packet"
    assert packet["schema_version"] == DELTA_PACKET_SCHEMA_VERSION
    assert packet["packet_id"].startswith("pmdelta_")
    assert len(packet["packet_digest"]) == 64
    assert len(packet["content_digest"]) == 64
    assert len(packet["evidence_digest"]) == 64
    assert packet["authority"] == {
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


def test_delta_packet_extracts_evidence_units_and_claim_candidates() -> None:
    packet = to_delta_packet(_page_map())
    unit_kinds = {unit["unit_kind"] for unit in packet["evidence_units"]}
    candidate_kinds = {candidate["candidate_kind"] for candidate in packet["claim_candidates"]}

    assert "title" in unit_kinds
    assert "statement_surface" in unit_kinds
    assert "proof_marker" in unit_kinds
    assert "interaction_ref" in unit_kinds
    assert "axiom_or_inference_rule_candidate" in candidate_kinds
    assert "theorem_candidate" in candidate_kinds
    assert all(candidate["truth_claim_opened"] is False for candidate in packet["claim_candidates"])
    assert all(candidate["native_adoption_opened"] is False for candidate in packet["claim_candidates"])


def test_delta_packet_is_deterministic_for_same_page_map() -> None:
    first = to_delta_packet(_page_map())
    second = to_delta_packet(_page_map())

    assert first["packet_digest"] == second["packet_digest"]
    assert first["evidence_units"] == second["evidence_units"]
    assert first["claim_candidates"] == second["claim_candidates"]


def test_delta_json_round_trips() -> None:
    data = json.loads(to_delta_json(_page_map()))

    assert data["record_kind"] == "pagemap_delta_intelligence_packet"
    assert data["source_uri"] == "https://us.metamath.org/mpeuni/ax-mp.html"


def test_delta_packet_rejects_invalid_source_observation_digest() -> None:
    with pytest.raises(ValueError, match="source_observation_digest"):
        to_delta_packet(_page_map(), source_observation_digest="not-a-digest")
