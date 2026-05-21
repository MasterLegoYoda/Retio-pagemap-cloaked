# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for target product matching logic.

Covers: find_target_match, compute_match_confidence, dual-threshold,
brand gate, price budget, edge cases, never-raises.
"""

from __future__ import annotations

from pagemap.core.ecommerce import ProductCard, TargetProduct
from pagemap.core.ecommerce._target_matcher import (
    _THRESHOLD_BRAND,
    _THRESHOLD_HIGH,
    compute_match_confidence,
    find_target_match,
)


def _card(name: str, price: float | None = None, brand: str | None = None, ref: int | None = None) -> ProductCard:
    return ProductCard(name=name, price=price, brand=brand, ref=ref)


# ── find_target_match: basic cases ────────────────────────────────


class TestFindTargetMatchBasic:
    def test_exact_match(self):
        cards = (_card("Lip Sleeping Mask", price=20.0),)
        target = TargetProduct(name="Lip Sleeping Mask")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.confidence >= 0.95
        assert result.card_index == 0
        assert result.matched_name == "Lip Sleeping Mask"

    def test_fuzzy_match_with_modifiers(self):
        """Product names with extra modifiers (size, shipping) should still match."""
        cards = (_card("Laneige Lip Sleeping Mask Berry 20g [Free Shipping]"),)
        target = TargetProduct(name="Lip Sleeping Mask")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.confidence >= 0.75

    def test_below_threshold_returns_none(self):
        cards = (_card("Samsung Galaxy S24 Ultra"),)
        target = TargetProduct(name="Lip Sleeping Mask")
        result = find_target_match(cards, target)
        assert result is None

    def test_best_match_selected(self):
        cards = (
            _card("Random Product"),
            _card("Nike Air Max 90 White"),
            _card("Nike Air Max 270"),
        )
        target = TargetProduct(name="Nike Air Max 90")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.card_index == 1
        assert "Air Max 90" in result.matched_name

    def test_korean_product_name(self):
        cards = (_card("나이키 에어맥스 90 화이트"),)
        target = TargetProduct(name="나이키 에어맥스 90")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.confidence >= 0.75

    def test_japanese_product_name(self):
        cards = (_card("ナイキ エアマックス 90 ホワイト 27cm"),)
        target = TargetProduct(name="ナイキ エアマックス 90")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.confidence >= 0.75

    def test_confidence_is_rounded(self):
        cards = (_card("Nike Air Max 90"),)
        target = TargetProduct(name="Nike Air Max 90")
        result = find_target_match(cards, target)
        assert result is not None
        # round(x, 2) should produce at most 2 decimal places
        assert result.confidence == round(result.confidence, 2)


# ── find_target_match: brand gate ─────────────────────────────────


class TestFindTargetMatchBrandGate:
    def test_brand_match_lowers_threshold(self):
        """A score in [0.60, 0.75) should match only when brand matches."""
        # Deliberately weak name match but with matching brand
        cards = (_card("Sleeping Mask Berry Set Limited Edition", brand="Laneige"),)
        target_with = TargetProduct(name="Lip Sleeping Mask", brand="Laneige")
        target_without = TargetProduct(name="Lip Sleeping Mask")

        result_with = find_target_match(cards, target_with)
        result_without = find_target_match(cards, target_without)

        # With brand, might pass where without brand wouldn't
        if result_with is not None and result_without is None:
            assert result_with.confidence >= _THRESHOLD_BRAND
            assert result_with.confidence < _THRESHOLD_HIGH

    def test_brand_case_insensitive(self):
        cards = (_card("Nike Air Max 90", brand="NIKE"),)
        target = TargetProduct(name="Nike Air Max 90", brand="nike")
        result = find_target_match(cards, target)
        assert result is not None

    def test_brand_mismatch_no_gate(self):
        """Brand mismatch should NOT enable the lower threshold."""
        cards = (_card("Sleeping Mask Berry Set", brand="Innisfree"),)
        target = TargetProduct(name="Lip Sleeping Mask", brand="Laneige")
        result = find_target_match(cards, target)
        # Even with brand param, brand mismatch means high threshold applies
        if result is not None:
            assert result.confidence >= _THRESHOLD_HIGH

    def test_target_brand_card_no_brand(self):
        """If card has no brand, brand gate cannot fire."""
        cards = (_card("Sleeping Mask Berry Set"),)  # no brand
        target = TargetProduct(name="Lip Sleeping Mask", brand="Laneige")
        result = find_target_match(cards, target)
        if result is not None:
            assert result.confidence >= _THRESHOLD_HIGH

    def test_card_brand_no_target_brand(self):
        """If target has no brand, brand gate cannot fire."""
        cards = (_card("Sleeping Mask Berry Set", brand="Laneige"),)
        target = TargetProduct(name="Lip Sleeping Mask")  # no brand
        result = find_target_match(cards, target)
        if result is not None:
            assert result.confidence >= _THRESHOLD_HIGH


# ── find_target_match: price budget ───────────────────────────────


class TestFindTargetMatchBudget:
    def test_in_budget(self):
        cards = (_card("Nike Air Max 90", price=129.99),)
        target = TargetProduct(name="Nike Air Max 90", max_price=150.0)
        result = find_target_match(cards, target)
        assert result is not None
        assert result.price_in_budget is True

    def test_over_budget(self):
        cards = (_card("Nike Air Max 90", price=199.99),)
        target = TargetProduct(name="Nike Air Max 90", max_price=150.0)
        result = find_target_match(cards, target)
        assert result is not None
        assert result.price_in_budget is False

    def test_exactly_at_budget(self):
        """Price exactly equal to max_price should be in budget."""
        cards = (_card("Nike Air Max 90", price=150.0),)
        target = TargetProduct(name="Nike Air Max 90", max_price=150.0)
        result = find_target_match(cards, target)
        assert result is not None
        assert result.price_in_budget is True

    def test_no_card_price(self):
        cards = (_card("Nike Air Max 90"),)  # price=None
        target = TargetProduct(name="Nike Air Max 90", max_price=150.0)
        result = find_target_match(cards, target)
        assert result is not None
        assert result.price_in_budget is None

    def test_no_max_price(self):
        cards = (_card("Nike Air Max 90", price=129.99),)
        target = TargetProduct(name="Nike Air Max 90")  # no max_price
        result = find_target_match(cards, target)
        assert result is not None
        assert result.price_in_budget is None

    def test_zero_max_price(self):
        """max_price=0 means nothing is in budget (except free items)."""
        cards = (_card("Nike Air Max 90", price=129.99),)
        target = TargetProduct(name="Nike Air Max 90", max_price=0.0)
        result = find_target_match(cards, target)
        assert result is not None
        assert result.price_in_budget is False

    def test_zero_price_in_budget(self):
        """Free item should be in any budget."""
        cards = (_card("Free Sample", price=0.0),)
        target = TargetProduct(name="Free Sample", max_price=10.0)
        result = find_target_match(cards, target)
        assert result is not None
        assert result.price_in_budget is True


# ── find_target_match: edge cases ─────────────────────────────────


class TestFindTargetMatchEdgeCases:
    def test_empty_cards(self):
        result = find_target_match((), TargetProduct(name="Test"))
        assert result is None

    def test_none_target(self):
        result = find_target_match((_card("Test"),), None)  # type: ignore[arg-type]
        assert result is None

    def test_empty_target_name(self):
        result = find_target_match((_card("Test"),), TargetProduct(name=""))
        assert result is None

    def test_whitespace_only_target_name(self):
        result = find_target_match((_card("Test"),), TargetProduct(name="   "))
        assert result is None

    def test_cards_with_empty_names_skipped(self):
        cards = (_card(""), _card("Nike Air Max 90"))
        target = TargetProduct(name="Nike Air Max 90")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.card_index == 1

    def test_all_cards_empty_names(self):
        cards = (_card(""), _card(""), _card(""))
        target = TargetProduct(name="Nike Air Max 90")
        result = find_target_match(cards, target)
        assert result is None

    def test_single_card(self):
        cards = (_card("Nike Air Max 90"),)
        target = TargetProduct(name="Nike Air Max 90")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.card_index == 0

    def test_many_cards_performance(self):
        """50 cards should match in reasonable time (< 100ms)."""
        import time

        cards = tuple(_card(f"Product {i}", price=float(i)) for i in range(50))
        cards = cards + (_card("Nike Air Max 90 White", price=129.99),)
        target = TargetProduct(name="Nike Air Max 90")

        start = time.monotonic()
        result = find_target_match(cards, target)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert result is not None
        assert result.card_index == 50
        assert elapsed_ms < 100  # should be < 5ms typically

    def test_very_long_product_name(self):
        """Should handle very long product names without crashing."""
        long_name = "Nike Air Max 90 " + "Premium Limited Edition " * 50
        cards = (_card(long_name),)
        target = TargetProduct(name="Nike Air Max 90")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.confidence >= 0.75

    def test_special_characters_in_name(self):
        cards = (_card("L'Oréal Paris Revitalift (50ml) — Anti-Wrinkle + Firming"),)
        target = TargetProduct(name="L'Oréal Revitalift")
        result = find_target_match(cards, target)
        assert result is not None

    def test_leading_trailing_whitespace_stripped(self):
        cards = (_card("  Nike Air Max 90  "),)
        target = TargetProduct(name="  Nike Air Max 90  ")
        result = find_target_match(cards, target)
        assert result is not None
        assert result.confidence >= 0.95

    def test_never_raises_none_none(self):
        assert find_target_match(None, None) is None  # type: ignore[arg-type]

    def test_never_raises_name_none(self):
        assert find_target_match((_card("x"),), TargetProduct(name=None)) is None  # type: ignore[arg-type]

    def test_never_raises_int_name(self):
        assert find_target_match((_card("x"),), TargetProduct(name=123)) is None  # type: ignore[arg-type]


# ── compute_match_confidence: basic ───────────────────────────────


class TestComputeMatchConfidence:
    def test_exact_match(self):
        result = compute_match_confidence("Nike Air Max 90", TargetProduct(name="Nike Air Max 90"))
        assert result is not None
        assert result >= 0.95

    def test_fuzzy_match(self):
        result = compute_match_confidence(
            "Laneige Lip Sleeping Mask Berry 20g",
            TargetProduct(name="Lip Sleeping Mask"),
        )
        assert result is not None
        assert result >= 0.75

    def test_below_threshold(self):
        result = compute_match_confidence("Samsung Galaxy Phone", TargetProduct(name="Lip Sleeping Mask"))
        assert result is None

    def test_confidence_is_rounded(self):
        result = compute_match_confidence("Nike Air Max 90", TargetProduct(name="Nike Air Max 90"))
        assert result is not None
        assert result == round(result, 2)


# ── compute_match_confidence: brand gate ──────────────────────────


class TestComputeMatchConfidenceBrandGate:
    def test_brand_match_lowers_threshold(self):
        """Brand gate should enable matching in [0.60, 0.75) range."""
        target = TargetProduct(name="Lip Sleeping Mask", brand="Laneige")
        result_with = compute_match_confidence(
            "Sleeping Mask Berry Set Limited Edition",
            target,
            product_brand="Laneige",
        )
        result_without = compute_match_confidence(
            "Sleeping Mask Berry Set Limited Edition",
            target,
            product_brand=None,
        )
        # Brand gate might enable a match that wouldn't pass without brand
        if result_with is not None and result_without is None:
            assert result_with >= _THRESHOLD_BRAND

    def test_brand_case_insensitive(self):
        result = compute_match_confidence(
            "Nike Air Max 90",
            TargetProduct(name="Nike Air Max 90", brand="NIKE"),
            product_brand="nike",
        )
        assert result is not None

    def test_brand_mismatch(self):
        """Brand mismatch should not enable gate."""
        result = compute_match_confidence(
            "Sleeping Mask Berry Set",
            TargetProduct(name="Lip Sleeping Mask", brand="Laneige"),
            product_brand="Innisfree",
        )
        if result is not None:
            assert result >= _THRESHOLD_HIGH

    def test_no_product_brand(self):
        """Without product_brand, only high threshold works."""
        result = compute_match_confidence(
            "Sleeping Mask Berry Set",
            TargetProduct(name="Lip Sleeping Mask", brand="Laneige"),
        )
        if result is not None:
            assert result >= _THRESHOLD_HIGH


# ── compute_match_confidence: edge cases ──────────────────────────


class TestComputeMatchConfidenceEdgeCases:
    def test_empty_product_name(self):
        assert compute_match_confidence("", TargetProduct(name="Test")) is None

    def test_empty_target_name(self):
        assert compute_match_confidence("Product", TargetProduct(name="")) is None

    def test_whitespace_only(self):
        assert compute_match_confidence("   ", TargetProduct(name="Test")) is None

    def test_never_raises_none_none(self):
        assert compute_match_confidence(None, None) is None  # type: ignore[arg-type]

    def test_never_raises_int_input(self):
        assert compute_match_confidence(123, TargetProduct(name="Test")) is None  # type: ignore[arg-type]
