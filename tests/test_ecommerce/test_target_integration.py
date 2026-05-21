# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Integration tests for target_product across engines and router.

Verifies that target_product flows correctly through:
- run_ecommerce_engine → search/listing/product engines
- Engine results contain target_match / match_confidence
- target_product=None preserves backward compatibility
"""

from __future__ import annotations

from pagemap.core.ecommerce import (
    TargetProduct,
    run_ecommerce_engine,
)

from .conftest import ITEMLIST_JSONLD, PRODUCT_JSONLD


def _make_interactables():
    from pagemap import Interactable

    return [
        Interactable(ref=1, role="button", name="Buy", affordance="click", region="main", tier=1),
    ]


# ── run_ecommerce_engine router ───────────────────────────────────


class TestRouterPassthrough:
    """Verify target_product parameter reaches each engine."""

    def test_search_engine_receives_target(self):
        result = run_ecommerce_engine(
            page_type="search_results",
            raw_html=f"<html>{ITEMLIST_JSONLD}</html>",
            html_lower=f"<html>{ITEMLIST_JSONLD}</html>".lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/search?q=product+a",
            navigation_hints={},
            target_product=TargetProduct(name="Product A"),
        )
        assert result is not None
        tm = result.get("target_match")
        assert tm is not None
        assert tm["confidence"] >= 0.75
        assert tm["matched_name"] == "Product A"
        assert tm["card_index"] == 0

    def test_search_engine_no_match(self):
        result = run_ecommerce_engine(
            page_type="search_results",
            raw_html=f"<html>{ITEMLIST_JSONLD}</html>",
            html_lower=f"<html>{ITEMLIST_JSONLD}</html>".lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/search?q=product",
            navigation_hints={},
            target_product=TargetProduct(name="Completely Unrelated XYZ"),
        )
        assert result is not None
        assert result.get("target_match") is None

    def test_search_engine_no_target(self):
        """target_product=None should produce no target_match."""
        result = run_ecommerce_engine(
            page_type="search_results",
            raw_html=f"<html>{ITEMLIST_JSONLD}</html>",
            html_lower=f"<html>{ITEMLIST_JSONLD}</html>".lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/search?q=product",
            navigation_hints={},
            target_product=None,
        )
        assert result is not None
        assert result.get("target_match") is None

    def test_listing_engine_receives_target(self):
        html = f"<html>{ITEMLIST_JSONLD}</html>"
        result = run_ecommerce_engine(
            page_type="listing",
            raw_html=html,
            html_lower=html.lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/category/shoes",
            navigation_hints={},
            target_product=TargetProduct(name="Product B"),
        )
        assert result is not None
        tm = result.get("target_match")
        assert tm is not None
        assert tm["matched_name"] == "Product B"

    def test_product_engine_receives_target(self):
        html = f"<html>{PRODUCT_JSONLD}</html>"
        result = run_ecommerce_engine(
            page_type="product_detail",
            raw_html=html,
            html_lower=html.lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/product/123",
            navigation_hints={},
            target_product=TargetProduct(name="오버핏 레더 자켓"),
        )
        assert result is not None
        mc = result.get("match_confidence")
        assert mc is not None
        assert mc >= 0.75

    def test_product_engine_brand_gate(self):
        """Product engine should pass brand to compute_match_confidence."""
        html = f"<html>{PRODUCT_JSONLD}</html>"
        # PRODUCT_JSONLD has brand "TestBrand" and name "오버핏 레더 자켓"
        result = run_ecommerce_engine(
            page_type="product_detail",
            raw_html=html,
            html_lower=html.lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/product/123",
            navigation_hints={},
            target_product=TargetProduct(name="오버핏 레더 자켓", brand="TestBrand"),
        )
        assert result is not None
        assert result.get("match_confidence") is not None

    def test_product_engine_no_target(self):
        html = f"<html>{PRODUCT_JSONLD}</html>"
        result = run_ecommerce_engine(
            page_type="product_detail",
            raw_html=html,
            html_lower=html.lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/product/123",
            navigation_hints={},
            target_product=None,
        )
        assert result is not None
        assert result.get("match_confidence") is None

    def test_unknown_page_type_returns_none(self):
        result = run_ecommerce_engine(
            page_type="article",
            raw_html="<html></html>",
            html_lower="<html></html>",
            interactables=[],
            metadata={},
            page_url="https://example.com/blog",
            navigation_hints={},
            target_product=TargetProduct(name="Test"),
        )
        assert result is None


# ── Backward compatibility ────────────────────────────────────────


class TestBackwardCompatibility:
    """Ensure target_product=None does not change existing behavior."""

    def test_search_result_unchanged(self):
        html = f"<html>{ITEMLIST_JSONLD}</html>"
        result_without = run_ecommerce_engine(
            page_type="search_results",
            raw_html=html,
            html_lower=html.lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/search?q=product",
            navigation_hints={},
        )
        result_with_none = run_ecommerce_engine(
            page_type="search_results",
            raw_html=html,
            html_lower=html.lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/search?q=product",
            navigation_hints={},
            target_product=None,
        )
        # Both should produce same cards, same structure
        assert result_without is not None
        assert result_with_none is not None
        assert len(result_without.get("cards", [])) == len(result_with_none.get("cards", []))
        assert result_without.get("target_match") is None
        assert result_with_none.get("target_match") is None

    def test_product_result_unchanged(self):
        html = f"<html>{PRODUCT_JSONLD}</html>"
        result = run_ecommerce_engine(
            page_type="product_detail",
            raw_html=html,
            html_lower=html.lower(),
            interactables=_make_interactables(),
            metadata={},
            page_url="https://example.com/product/123",
            navigation_hints={},
        )
        assert result is not None
        assert result.get("name") == "오버핏 레더 자켓"
        assert result.get("match_confidence") is None


# ── Diagnostics integration ───────────────────────────────────────


class TestDiagnosticsIntegration:
    """Verify target_product-aware suggested actions."""

    def test_empty_results_with_target(self):
        from pagemap.core.diagnostics import PageFailureState, PageStateDiagnosis
        from pagemap.core.diagnostics.suggested_actions import suggest_page_recovery

        diag = PageStateDiagnosis(
            state=PageFailureState.EMPTY_RESULTS,
            confidence=0.9,
            signals=(),
        )
        target = TargetProduct(name="Nike Air Max 90")
        actions = suggest_page_recovery(diag, target_product=target)
        assert len(actions) >= 1
        assert "Nike Air Max 90" in actions[0].reason

    def test_out_of_stock_with_target(self):
        from pagemap.core.diagnostics import PageFailureState, PageStateDiagnosis
        from pagemap.core.diagnostics.suggested_actions import suggest_page_recovery

        diag = PageStateDiagnosis(
            state=PageFailureState.OUT_OF_STOCK,
            confidence=0.85,
            signals=(),
        )
        target = TargetProduct(name="Laneige Lip Sleeping Mask")
        actions = suggest_page_recovery(diag, target_product=target)
        assert len(actions) >= 2
        assert "Laneige Lip Sleeping Mask" in actions[1].reason

    def test_empty_results_without_target(self):
        from pagemap.core.diagnostics import PageFailureState, PageStateDiagnosis
        from pagemap.core.diagnostics.suggested_actions import suggest_page_recovery

        diag = PageStateDiagnosis(
            state=PageFailureState.EMPTY_RESULTS,
            confidence=0.9,
            signals=(),
        )
        actions = suggest_page_recovery(diag)
        assert len(actions) >= 1
        assert "broader search" in actions[0].reason

    def test_bot_blocked_ignores_target(self):
        """BOT_BLOCKED suggestions should not change with target_product."""
        from pagemap.core.diagnostics import PageFailureState, PageStateDiagnosis
        from pagemap.core.diagnostics.suggested_actions import suggest_page_recovery

        diag = PageStateDiagnosis(
            state=PageFailureState.BOT_BLOCKED,
            confidence=0.95,
            signals=(),
        )
        actions_without = suggest_page_recovery(diag)
        actions_with = suggest_page_recovery(diag, target_product=TargetProduct(name="Test"))
        assert len(actions_without) == len(actions_with)
        assert actions_without[0].reason == actions_with[0].reason
