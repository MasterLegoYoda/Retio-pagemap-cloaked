"""Capability bitmask for :mod:`pagemap.pipeline.extractor`.

A :class:`~enum.IntFlag` is used so capabilities compose and serialize
as a single integer in tool results.  Adding a new bit is a
backward-compatible change as long as downstream code uses the
``in`` operator (not equality).

The current bits are:

* :attr:`MARKDOWN` — the extractor emits a markdown / text body.
* :attr:`INTERACTABLES` — the extractor emits ref-numbered
  interactable elements (buttons, links, inputs) so an agent can
  act on the page.
* :attr:`FORMS` — the extractor preserves form fields and their
  current values, so an agent can fill and submit forms.
* :attr:`PAGE_TYPE` — the extractor classifies the page (e.g.
  ``product_detail``, ``article``, ``search_results``).
* :attr:`SCHEMA` — the extractor emits structured metadata
  (JSON-LD, OpenGraph) suitable for downstream reasoning.

Pulpie, for example, only declares :attr:`MARKDOWN` because its
``Extractor`` API returns kept-block HTML/markdown without form-state
preservation.  Retio declares all five because PageMap is built on
the live AX tree + a full DOM pass.
"""

from __future__ import annotations

from enum import IntFlag


class Capability(IntFlag):
    """Capability flags advertised by an :class:`Extractor`.

    Bits are powers of two starting at 1.  ``Capability(0)`` is the
    empty flagset and means "the extractor emits nothing useful" —
    nothing should ever have an empty capability set, so callers can
    treat that as a programming error.
    """

    NONE = 0
    MARKDOWN = 1
    INTERACTABLES = 2
    FORMS = 4
    PAGE_TYPE = 8
    SCHEMA = 16


#: Human-readable name for each capability bit, indexed by the bit
#: value (not the bit position).  Used by tool descriptions and
#: ``MissingCapability`` error messages.
CAPABILITY_NAMES: dict[int, str] = {
    int(Capability.MARKDOWN): "markdown",
    int(Capability.INTERACTABLES): "interactables",
    int(Capability.FORMS): "forms",
    int(Capability.PAGE_TYPE): "page_type",
    int(Capability.SCHEMA): "schema",
}

#: Long-form description for each capability bit, used in user-facing
#: tool output and documentation.
CAPABILITY_DESCRIPTIONS: dict[int, str] = {
    int(Capability.MARKDOWN): (
        "Emits a markdown / text body suitable for LLM context."
    ),
    int(Capability.INTERACTABLES): (
        "Emits ref-numbered interactable elements (buttons, links, "
        "inputs) so an agent can act on the page."
    ),
    int(Capability.FORMS): (
        "Preserves form fields and their current values, so an "
        "agent can fill and submit forms."
    ),
    int(Capability.PAGE_TYPE): (
        "Classifies the page (e.g. product_detail, article, "
        "search_results)."
    ),
    int(Capability.SCHEMA): (
        "Emits structured metadata (JSON-LD, OpenGraph) suitable "
        "for downstream reasoning."
    ),
}


#: Set of capability bits that are required to call ``get_page_map``.
#: Used by the server to pre-flight check the configured pipeline.
GET_PAGE_MAP_REQUIRED: Capability = (
    Capability.INTERACTABLES
    | Capability.PAGE_TYPE
    | Capability.SCHEMA
)

#: Set of capability bits that are required to call ``web_fetch``.
WEB_FETCH_REQUIRED: Capability = Capability.MARKDOWN

#: Set of capability bits required by browser-only tools
#: (``execute_action``, ``fill_form``, etc.).
BROWSER_TOOLS_REQUIRED: Capability = (
    Capability.INTERACTABLES | Capability.FORMS
)


def capability_name(cap: Capability) -> str:
    """Return the canonical name for a single-bit capability."""
    if cap not in CAPABILITY_NAMES:
        return f"unknown({int(cap)})"
    return CAPABILITY_NAMES[int(cap)]


def capability_description(cap: Capability) -> str:
    """Return the human-readable description for a single-bit capability."""
    if cap not in CAPABILITY_DESCRIPTIONS:
        return f"unknown capability (bit={int(cap)})"
    return CAPABILITY_DESCRIPTIONS[int(cap)]


__all__ = [
    "CAPABILITY_DESCRIPTIONS",
    "CAPABILITY_NAMES",
    "Capability",
    "capability_description",
    "capability_name",
]
