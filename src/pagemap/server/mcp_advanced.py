# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""MCP Structured Output models and tool output schema registry.

Defines Pydantic v2 output models for all 9 MCP tools, a schema registry
mapping tool names to their output models, and server-level task support
configuration.

When integrated with ``@mcp.tool(structured_output=True)``, the SDK:
1. Generates ``output_schema`` JSON Schema from the return type annotation.
2. ``convert_result()`` transforms a Pydantic model into
   ``(unstructured_content, structured_content)`` tuple.
3. The lowlevel server builds ``CallToolResult(content=..., structuredContent=...)``.
4. ``jsonschema.validate()`` verifies ``structuredContent`` against ``outputSchema``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Enums ───────────────────────────────────────────────────────────────


class ChangeType(StrEnum):
    """Type of page change detected after an action."""

    none = "none"
    content = "content"
    navigation = "navigation"
    dialog = "dialog"
    download = "download"


# ── Structured Output Models ────────────────────────────────────────────


class NavigationHint(BaseModel):
    """A hint about a navigation target on the page."""

    ref: int = Field(description="Element ref number")
    label: str = Field(description="Human-readable label")
    url: str | None = Field(default=None, description="Target URL if available")


class PageMetadata(BaseModel):
    """Page-level metadata extracted during page map generation."""

    language: str | None = Field(default=None, description="Detected page language (ISO 639-1)")
    viewport_width: int | None = Field(default=None, description="Viewport width in pixels")
    viewport_height: int | None = Field(default=None, description="Viewport height in pixels")
    scroll_position: int | None = Field(default=None, description="Current vertical scroll offset")
    total_height: int | None = Field(default=None, description="Total page height in pixels")


class GetPageMapResult(BaseModel):
    """Structured output for the ``get_page_map`` tool."""

    url: str = Field(description="Current page URL")
    title: str = Field(description="Page title")
    page_type: str = Field(default="unknown", description="Detected page type")
    interactables: int = Field(description="Number of interactive elements")
    pruned_context: str = Field(description="Pruned page content text")
    pruned_tokens: int = Field(description="Approximate token count of pruned context")
    generation_ms: float = Field(description="Time to generate the page map in milliseconds")
    metadata: PageMetadata | None = Field(default=None, description="Page metadata")
    navigation_hints: list[NavigationHint] = Field(default_factory=list, description="Navigation hints")
    warnings: list[str] = Field(default_factory=list, description="Warnings encountered during generation")

    def __str__(self) -> str:
        return self.pruned_context


class DialogInfo(BaseModel):
    """Information about a browser dialog that appeared."""

    type: str = Field(description="Dialog type: alert, confirm, prompt, beforeunload")
    message: str = Field(description="Dialog message text")
    accepted: bool = Field(default=True, description="Whether the dialog was accepted")


class ChangeDetails(BaseModel):
    """Details about what changed on the page after an action."""

    old_url: str | None = Field(default=None, description="Previous URL before navigation")
    new_url: str | None = Field(default=None, description="New URL after navigation")
    description: str = Field(default="", description="Human-readable change description")


class ExecuteActionResult(BaseModel):
    """Structured output for the ``execute_action`` tool."""

    description: str = Field(description="Human-readable description of what happened")
    current_url: str = Field(description="Current page URL after action")
    change: ChangeType = Field(default=ChangeType.none, description="Type of page change detected")
    refs_expired: bool = Field(default=True, description="Whether ref numbers need refreshing")
    change_details: ChangeDetails | None = Field(default=None, description="Details about the change")
    dialogs: list[DialogInfo] = Field(default_factory=list, description="Dialogs that appeared")

    def __str__(self) -> str:
        data: dict[str, Any] = {
            "description": self.description,
            "current_url": self.current_url,
            "change": self.change.value,
            "refs_expired": self.refs_expired,
        }
        if self.change_details is not None:
            data["change_details"] = self.change_details.model_dump()
        if self.dialogs:
            data["dialogs"] = [d.model_dump() for d in self.dialogs]
        return json.dumps(data, ensure_ascii=False)


class GetPageStateResult(BaseModel):
    """Structured output for the ``get_page_state`` tool."""

    url: str = Field(description="Current page URL")
    title: str = Field(description="Page title")
    has_page_map: bool = Field(description="Whether a page map is currently cached")
    scroll_y: int = Field(default=0, description="Current vertical scroll position")
    viewport_height: int = Field(default=0, description="Viewport height in pixels")
    total_height: int = Field(default=0, description="Total page height in pixels")

    def __str__(self) -> str:
        return json.dumps(
            {"url": self.url, "title": self.title, "has_page_map": self.has_page_map},
            ensure_ascii=False,
            indent=2,
        )


class NavigateBackResult(BaseModel):
    """Structured output for the ``navigate_back`` tool."""

    previous_url: str = Field(description="URL before navigating back")
    current_url: str = Field(description="URL after navigating back")
    refs_expired: bool = Field(default=True, description="Whether ref numbers need refreshing")

    def __str__(self) -> str:
        return f"Navigated back to: {self.current_url}\n\nRefs are now expired. Call get_page_map to get fresh refs."


class ScrollPageResult(BaseModel):
    """Structured output for the ``scroll_page`` tool."""

    direction: str = Field(description="Scroll direction: up or down")
    scroll_y: int = Field(description="New vertical scroll position")
    viewport_height: int = Field(default=0, description="Viewport height in pixels")
    total_height: int = Field(default=0, description="Total page height in pixels")
    at_top: bool = Field(default=False, description="Whether scroll reached the top")
    at_bottom: bool = Field(default=False, description="Whether scroll reached the bottom")

    def __str__(self) -> str:
        meta = json.dumps(
            {
                "scrollY": self.scroll_y,
                "viewportHeight": self.viewport_height,
                "atTop": self.at_top,
                "atBottom": self.at_bottom,
            },
            indent=2,
        )
        return f"Scrolled {self.direction}.\n{meta}\n\nCall get_page_map to get refs for visible content."


class FormFieldResult(BaseModel):
    """Result of a single form field operation."""

    ref: int = Field(description="Element ref number")
    action: str = Field(description="Action performed: type, select, click")
    success: bool = Field(description="Whether the field operation succeeded")
    error: str | None = Field(default=None, description="Error message if failed")


class FillFormResult(BaseModel):
    """Structured output for the ``fill_form`` tool."""

    fields_completed: int = Field(description="Number of fields successfully completed")
    results: list[FormFieldResult] = Field(description="Per-field results")

    def __str__(self) -> str:
        total = len(self.results)
        lines = [f"fill_form: {self.fields_completed}/{total} fields completed."]
        for r in self.results:
            status = "OK" if r.success else f"FAIL: {r.error}"
            lines.append(f"  ref={r.ref} {r.action}: {status}")
        return "\n".join(lines)


class WaitForResult(BaseModel):
    """Structured output for the ``wait_for`` tool."""

    condition_met: bool = Field(description="Whether the wait condition was met before timeout")
    elapsed_ms: float = Field(description="Time spent waiting in milliseconds")

    def __str__(self) -> str:
        if self.condition_met:
            return f"Wait condition met after {self.elapsed_ms:.1f}ms."
        return f"Wait condition NOT met after {self.elapsed_ms:.1f}ms (timeout)."


class BatchPageMapEntry(BaseModel):
    """A single entry in batch page map results."""

    url: str = Field(description="Requested URL")
    success: bool = Field(description="Whether the page map was generated")
    page_map: GetPageMapResult | None = Field(default=None, description="Page map result if successful")
    error: str | None = Field(default=None, description="Error message if failed")


class BatchGetPageMapResult(BaseModel):
    """Structured output for the ``batch_get_page_map`` tool."""

    total: int = Field(description="Total URLs requested")
    succeeded: int = Field(description="Number of successful page maps")
    failed: int = Field(description="Number of failed page maps")
    results: list[BatchPageMapEntry] = Field(description="Per-URL results")

    def __str__(self) -> str:
        return json.dumps(
            {"total": self.total, "succeeded": self.succeeded, "failed": self.failed},
            ensure_ascii=False,
        )


class ToolError(BaseModel):
    """RFC 9457 Problem Details-compatible error response for MCP tools.

    Returned when a tool invocation fails. Compatible with the project's
    ``ProblemDetail`` dataclass but specialized for MCP structured output.
    """

    error: str = Field(description="Human-readable error description")
    type: str = Field(default="about:blank", description="Error type URI (RFC 9457)")
    status: int = Field(default=500, description="HTTP-equivalent status code")
    refs_expired: bool = Field(default=False, description="Whether ref numbers need refreshing")
    recovery_hint: str = Field(default="", description="Suggested recovery action for the agent")


# ── Web fetch / search output models ─────────────────────────────────


class WebSearchOutputModel(BaseModel):
    """Structured output for the ``web_search`` tool."""

    query: str = Field(description="The query that was executed")
    provider: str = Field(description="Provider used to satisfy the query")
    session: str = Field(description="Session id that handled the request")
    session_created: bool = Field(
        default=False, description="True if a new session was created during this call"
    )
    result_count: int = Field(description="Number of results returned")
    results: list[WebSearchEntryModel] = Field(default_factory=list, description="Search results")
    elapsed_ms: float = Field(default=0.0, description="Wall-clock time in milliseconds")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")


class WebSearchEntryModel(BaseModel):
    """A single entry in a web search result list."""

    title: str = Field(description="Result title")
    url: str = Field(description="Result URL")
    snippet: str = Field(default="", description="Short text excerpt")
    source: str | None = Field(default=None, description="Provider name (e.g. 'duckduckgo')")


class WebFetchOutputModel(BaseModel):
    """Structured output for the ``web_fetch`` tool."""

    url: str = Field(description="The URL that was fetched (after redirects)")
    final_url: str | None = Field(
        default=None, description="Final URL after redirects (same as ``url`` if unchanged)"
    )
    title: str | None = Field(default=None, description="Page title if available")
    content_type: str | None = Field(default=None, description="HTTP content-type header")
    status: int | None = Field(default=None, description="HTTP status code")
    session: str = Field(description="Session id that handled the request")
    session_created: bool = Field(
        default=False, description="True if a new session was created during this call"
    )
    format: str = Field(description="Output format that produced ``content``")
    mode: str = Field(description="Fetch mode used (browser/fast)")
    content: str = Field(default="", description="Extracted content (truncated if too large)")
    content_length: int = Field(default=0, description="Length of the extracted content in chars")
    truncated: bool = Field(default=False, description="True if ``content`` was truncated")
    full_output_path: str | None = Field(
        default=None,
        description="Path to the un-truncated content when ``truncated`` is true",
    )
    elapsed_ms: float = Field(default=0.0, description="Wall-clock time in milliseconds")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Provider-specific metadata")


class BatchWebFetchOutputModel(BaseModel):
    """Structured output for the ``batch_web_fetch`` tool."""

    total: int = Field(description="Total URLs requested")
    succeeded: int = Field(description="Number of successful fetches")
    failed: int = Field(description="Number of failed fetches")
    session: str = Field(description="Session id that handled the requests")
    session_created: bool = Field(
        default=False, description="True if a new session was created during this call"
    )
    elapsed_ms: float = Field(default=0.0, description="Wall-clock time in milliseconds")
    results: list[BatchWebFetchEntryModel] = Field(
        default_factory=list, description="Per-URL results"
    )


class BatchWebFetchEntryModel(BaseModel):
    """A single entry in a batch fetch result."""

    url: str = Field(description="Requested URL")
    success: bool = Field(description="Whether the fetch succeeded")
    result: WebFetchOutputModel | None = Field(default=None, description="Result when successful")
    error: str | None = Field(default=None, description="Error message when failed")


class SessionInfoModel(BaseModel):
    """Summary view of an active web session."""

    id: str = Field(description="Session id")
    created_at: float = Field(description="time.time() when created")
    last_used: float = Field(description="time.time() when last used")
    history_size: int = Field(description="Number of recorded activities")
    is_default: bool = Field(description="True if this is the long-lived default session")


class SessionListOutputModel(BaseModel):
    """Structured output for the ``web_list_sessions`` tool."""

    sessions: list[SessionInfoModel] = Field(default_factory=list, description="Active sessions")


class SessionCloseOutputModel(BaseModel):
    """Structured output for the ``web_close_session`` tool."""

    closed: bool = Field(description="True when a session was closed or reset")
    session: str = Field(description="The session id that was acted on")


# ── Output Schema Registry ──────────────────────────────────────────────

#: Maps tool names to their Pydantic output model, or ``None`` for tools
#: that cannot return structured output (e.g., ``take_screenshot`` returns images).
TOOL_OUTPUT_SCHEMAS: dict[str, type[BaseModel] | None] = {
    "get_page_map": GetPageMapResult,
    "execute_action": ExecuteActionResult,
    "get_page_state": GetPageStateResult,
    "take_screenshot": None,  # Image binary — structured output not applicable
    "navigate_back": NavigateBackResult,
    "scroll_page": ScrollPageResult,
    "fill_form": FillFormResult,
    "wait_for": WaitForResult,
    "batch_get_page_map": BatchGetPageMapResult,
    "open_tab": None,
    "switch_tab": None,
    "list_tabs": None,
    "close_tab": None,
    # Web fetch / search
    "web_search": WebSearchOutputModel,
    "web_fetch": WebFetchOutputModel,
    "batch_web_fetch": BatchWebFetchOutputModel,
    "web_list_sessions": SessionListOutputModel,
    "web_close_session": SessionCloseOutputModel,
}


def get_output_schema(tool_name: str) -> dict[str, Any] | None:
    """Return the JSON Schema for a tool's structured output.

    Uses ``model_json_schema(mode="serialization")`` so the schema reflects
    how the model is serialized (not how it's validated on input).

    Returns ``None`` if the tool has no structured output model.
    """
    model = TOOL_OUTPUT_SCHEMAS.get(tool_name)
    if model is None:
        return None
    return model.model_json_schema(mode="serialization")


# ── Task Support Configuration ──────────────────────────────────────────


@dataclass(frozen=True)
class TaskSupportConfig:
    """Server-level task support configuration.

    MCP SDK's Task support is an **infrastructure-level** concern
    (``TaskSupport.in_memory()``), not per-tool. This config captures the
    server-wide settings.

    Tool-level task suitability is documented here for reference:
    - Task-suitable (long-running): ``get_page_map``, ``batch_get_page_map``
    - Immediate response: ``execute_action``, ``fill_form``, ``get_page_state``,
      ``take_screenshot``, ``navigate_back``, ``scroll_page``, ``wait_for``
    """

    enabled: bool = False
    store_type: str = "in_memory"  # "in_memory" | "redis"
    default_ttl_ms: int = 60_000  # 1 minute
