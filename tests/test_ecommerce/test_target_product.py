# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for TargetProduct and TargetMatch dataclasses."""

from __future__ import annotations

from pagemap.core.ecommerce import TargetMatch, TargetProduct


class TestTargetProduct:
    def test_create_with_name_only(self):
        tp = TargetProduct(name="Nike Air Max 90")
        assert tp.name == "Nike Air Max 90"
        assert tp.brand is None
        assert tp.max_price is None

    def test_create_with_all_fields(self):
        tp = TargetProduct(name="Lip Sleeping Mask", brand="Laneige", max_price=25.0)
        assert tp.name == "Lip Sleeping Mask"
        assert tp.brand == "Laneige"
        assert tp.max_price == 25.0

    def test_frozen(self):
        tp = TargetProduct(name="Test")
        try:
            tp.name = "Other"  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except AttributeError:
            pass


class TestTargetMatch:
    def test_create_basic(self):
        tm = TargetMatch(card_index=0, confidence=0.95, matched_name="Nike Air Max 90")
        assert tm.card_index == 0
        assert tm.confidence == 0.95
        assert tm.matched_name == "Nike Air Max 90"
        assert tm.price_in_budget is None

    def test_create_with_budget(self):
        tm = TargetMatch(card_index=2, confidence=0.85, matched_name="Product", price_in_budget=True)
        assert tm.price_in_budget is True

    def test_frozen(self):
        tm = TargetMatch(card_index=0, confidence=0.9, matched_name="Test")
        try:
            tm.confidence = 0.5  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except AttributeError:
            pass
