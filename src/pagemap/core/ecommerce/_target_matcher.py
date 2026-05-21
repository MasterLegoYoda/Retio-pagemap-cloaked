# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Target product matching — fuzzy match product cards against a target.

Uses rapidfuzz token_set_ratio for ecommerce product name matching,
where product names always contain extra modifiers (size, color, shipping).

Never raises — returns None on failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ProductCard, TargetMatch, TargetProduct

logger = logging.getLogger(__name__)

# Dual threshold: name-only ≥ 0.75, brand-backed ≥ 0.60
_THRESHOLD_HIGH = 0.75
_THRESHOLD_BRAND = 0.60


def find_target_match(
    cards: tuple[ProductCard, ...],
    target: TargetProduct,
) -> TargetMatch | None:
    """Find the best matching card for a target product. Never raises.

    Uses token_set_ratio with dual-threshold + brand gate:
    - score ≥ 0.75: name match alone is sufficient
    - score ≥ 0.60 + brand match: brand backs up a weaker name match
    - score < 0.60: no match

    Returns:
        TargetMatch for the best card, or None if no card meets threshold.
    """
    try:
        if not cards or not target or not target.name:
            return None

        from rapidfuzz.fuzz import token_set_ratio

        best_idx: int | None = None
        best_score: float = 0.0
        best_name: str = ""
        target_name = target.name.strip()

        for i, card in enumerate(cards):
            if not card.name:
                continue
            score = token_set_ratio(target_name, card.name.strip()) / 100.0

            # Dual threshold with brand gate
            brand_match = (
                target.brand is not None and card.brand is not None and target.brand.lower() == card.brand.lower()
            )

            if score >= _THRESHOLD_HIGH:
                pass  # name alone is sufficient
            elif score >= _THRESHOLD_BRAND and brand_match:
                pass  # brand backs up weaker name match
            else:
                continue  # below both thresholds

            if score > best_score:
                best_score = score
                best_idx = i
                best_name = card.name

        if best_idx is None:
            return None

        from . import TargetMatch

        # Price budget check
        price_in_budget: bool | None = None
        if target.max_price is not None:
            card_price = cards[best_idx].price
            if card_price is not None:
                price_in_budget = card_price <= target.max_price

        return TargetMatch(
            card_index=best_idx,
            confidence=round(best_score, 2),
            matched_name=best_name,
            price_in_budget=price_in_budget,
        )

    except Exception as e:
        logger.debug("Target matcher error: %s", e)
        return None


def compute_match_confidence(
    product_name: str,
    target: TargetProduct,
    product_brand: str | None = None,
) -> float | None:
    """Compute match confidence for a single product name against target. Never raises.

    Used for product_detail pages where there's a single product, not a list of cards.

    Args:
        product_name: The product's extracted name.
        target: The target product to match against.
        product_brand: The product's brand (optional, enables brand gate).

    Returns:
        Confidence 0.0-1.0 if match meets threshold, None otherwise.
    """
    try:
        if not product_name or not target or not target.name:
            return None

        from rapidfuzz.fuzz import token_set_ratio

        score = token_set_ratio(target.name.strip(), product_name.strip()) / 100.0

        # Dual threshold with brand gate
        brand_match = (
            target.brand is not None and product_brand is not None and target.brand.lower() == product_brand.lower()
        )

        if score >= _THRESHOLD_HIGH or (score >= _THRESHOLD_BRAND and brand_match):
            return round(score, 2)
        return None

    except Exception as e:
        logger.debug("Match confidence error: %s", e)
        return None
