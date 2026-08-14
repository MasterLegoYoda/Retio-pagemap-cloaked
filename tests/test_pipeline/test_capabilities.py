# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for :mod:`pagemap.pipeline.extractor.capabilities`.

Covers:

* Bitmask math — composition, ``in`` checks, equality.
* Name + description lookup.
* The pipeline-level pre-flight constants
  (``GET_PAGE_MAP_REQUIRED``, ``WEB_FETCH_REQUIRED``,
  ``BROWSER_TOOLS_REQUIRED``).
"""

from __future__ import annotations

from pagemap.pipeline.extractor.capabilities import (
    BROWSER_TOOLS_REQUIRED as _BROWSER_TOOLS_REQUIRED,
    CAPABILITY_DESCRIPTIONS,
    CAPABILITY_NAMES,
    GET_PAGE_MAP_REQUIRED as _GET_PAGE_MAP_REQUIRED,
    WEB_FETCH_REQUIRED as _WEB_FETCH_REQUIRED,
    Capability,
    capability_description,
    capability_name,
)


class TestCapability:
    def test_each_bit_has_unique_int_value(self):
        """Each declared capability has a distinct power of two."""
        bits = [
            Capability.MARKDOWN,
            Capability.INTERACTABLES,
            Capability.FORMS,
            Capability.PAGE_TYPE,
            Capability.SCHEMA,
        ]
        for bit in bits:
            # Power of two: only one bit set.
            assert bit > 0
            assert bit & (bit - 1) == 0
        # And they're all distinct.
        assert len(set(int(b) for b in bits)) == len(bits)

    def test_in_operator_with_combined_flag(self):
        combined = Capability.MARKDOWN | Capability.INTERACTABLES
        assert Capability.MARKDOWN in combined
        assert Capability.INTERACTABLES in combined
        assert Capability.FORMS not in combined

    def test_names_and_descriptions_complete(self):
        for bit in [
            Capability.MARKDOWN,
            Capability.INTERACTABLES,
            Capability.FORMS,
            Capability.PAGE_TYPE,
            Capability.SCHEMA,
        ]:
            assert int(bit) in CAPABILITY_NAMES
            assert int(bit) in CAPABILITY_DESCRIPTIONS

    def test_capability_name_lookup(self):
        assert capability_name(Capability.MARKDOWN) == "markdown"
        assert capability_name(Capability.INTERACTABLES) == "interactables"
        assert capability_name(Capability.FORMS) == "forms"
        assert capability_name(Capability.PAGE_TYPE) == "page_type"
        assert capability_name(Capability.SCHEMA) == "schema"

    def test_capability_description_is_meaningful(self):
        for bit in [
            Capability.MARKDOWN,
            Capability.INTERACTABLES,
            Capability.FORMS,
            Capability.PAGE_TYPE,
            Capability.SCHEMA,
        ]:
            desc = capability_description(bit)
            assert desc
            assert desc[0].isupper()  # Sentences start with a capital.

    def test_retio_capabilities_set(self):
        # The "retio" extractor advertises all five capabilities.
        from pagemap.pipeline.extractor.retio import RetioExtractor

        e = RetioExtractor()
        all_caps = (
            Capability.MARKDOWN
            | Capability.INTERACTABLES
            | Capability.FORMS
            | Capability.PAGE_TYPE
            | Capability.SCHEMA
        )
        assert e.capabilities == all_caps

    def test_pulpie_capabilities_set(self):
        # The "pulpie" extractor advertises MARKDOWN only.
        from pagemap.pipeline.extractor.pulpie import PulpieExtractor

        e = PulpieExtractor()
        assert e.capabilities == Capability.MARKDOWN
        assert Capability.INTERACTABLES not in e.capabilities
        assert Capability.FORMS not in e.capabilities

    def test_markdown_capabilities_set(self):
        # The "markdown" extractor advertises MARKDOWN only.
        from pagemap.pipeline.extractor.markdown import MarkdownExtractor

        e = MarkdownExtractor()
        assert e.capabilities == Capability.MARKDOWN


class TestPreFlightConstants:
    def test_get_page_map_requires_interactables(self):
        assert Capability.INTERACTABLES in _GET_PAGE_MAP_REQUIRED

    def test_web_fetch_requires_markdown(self):
        assert Capability.MARKDOWN in _WEB_FETCH_REQUIRED

    def test_browser_tools_require_interactables_and_forms(self):
        assert Capability.INTERACTABLES in _BROWSER_TOOLS_REQUIRED
        assert Capability.FORMS in _BROWSER_TOOLS_REQUIRED


class TestMissingCapabilityMessage:
    def test_error_text_mentions_capability_and_extractor(self):
        from pagemap.pipeline.extractor.errors import MissingCapability

        err = MissingCapability(
            pipeline_name="cloak-pulpie",
            extractor_name="pulpie",
            capability=int(Capability.INTERACTABLES),
            tool="get_page_map",
        )
        msg = str(err)
        assert "INTERACTABLES" in msg
        assert "pulpie" in msg
        assert "cloak-pulpie" in msg
        assert "get_page_map" in msg
        assert "--extractor retio" in msg  # default hint mentions retio
