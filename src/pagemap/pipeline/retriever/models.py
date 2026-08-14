"""Pydantic models for the web fetch / search layer."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Enums ────────────────────────────────────────────────────────────


class FetchMode(StrEnum):
    """Backend used by ``web_fetch``."""

    browser = "browser"
    fast = "fast"


class FetchFormat(StrEnum):
    """Output format produced by ``web_fetch``."""

    markdown = "markdown"
    text = "text"
    html = "html"
    json = "json"


class SearchProviderName(StrEnum):
    """Identifier for a search provider implementation."""

    duckduckgo = "duckduckgo"
    brave = "brave"
    bing = "bing"
    google = "google"
    searxng = "searxng"
    exa = "exa"
    tavily = "tavily"
    firecrawl = "firecrawl"


# ── Search ───────────────────────────────────────────────────────────


class WebSearchResult(BaseModel):
    """A single search result entry."""

    title: str = Field(description="Result title")
    url: str = Field(description="Result URL")
    snippet: str = Field(default="", description="Short text excerpt")
    source: str | None = Field(default=None, description="Provider name (e.g. 'duckduckgo')")


class WebSearchOutput(BaseModel):
    """Structured output for the ``web_search`` tool."""

    query: str = Field(description="The query that was executed")
    provider: str = Field(description="Provider used to satisfy the query")
    session: str = Field(description="Session id that handled the request")
    session_created: bool = Field(
        default=False,
        description="True if a new session was created during this call",
    )
    result_count: int = Field(description="Number of results returned")
    results: list[WebSearchResult] = Field(default_factory=list, description="Search results")
    elapsed_ms: float = Field(default=0.0, description="Wall-clock time in milliseconds")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")

    def __str__(self) -> str:
        return self.to_markdown()

    def to_markdown(self) -> str:
        lines: list[str] = [
            f"# Search: {self.query}",
            f"_provider={self.provider} session={self.session} results={self.result_count} "
            f"elapsed={self.elapsed_ms:.0f}ms_",
            "",
        ]
        for i, r in enumerate(self.results, start=1):
            title = r.title or "(no title)"
            url = r.url or ""
            snippet = r.snippet.strip()
            lines.append(f"{i}. [{title}]({url})")
            if snippet:
                lines.append(f"   {snippet}")
        if self.warnings:
            lines.append("")
            lines.append("**Warnings:**")
            for w in self.warnings:
                lines.append(f"- {w}")
        return "\n".join(lines)


# ── Fetch ────────────────────────────────────────────────────────────


class WebFetchResult(BaseModel):
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
        default=False,
        description="True if a new session was created during this call",
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

    def __str__(self) -> str:
        if self.format in ("markdown", "text", "html"):
            return self.content
        # JSON fallback
        import json

        return json.dumps(self.model_dump(), ensure_ascii=False, indent=2)


# ── Batch fetch ──────────────────────────────────────────────────────


class BatchWebFetchEntry(BaseModel):
    """A single entry in batch fetch results."""

    url: str = Field(description="Requested URL")
    success: bool = Field(description="Whether the fetch succeeded")
    result: WebFetchResult | None = Field(default=None, description="Result when successful")
    error: str | None = Field(default=None, description="Error message when failed")


class BatchWebFetchResult(BaseModel):
    """Structured output for the ``batch_web_fetch`` tool."""

    total: int = Field(description="Total URLs requested")
    succeeded: int = Field(description="Number of successful fetches")
    failed: int = Field(description="Number of failed fetches")
    session: str = Field(description="Session id that handled the requests")
    session_created: bool = Field(
        default=False,
        description="True if a new session was created during this call",
    )
    elapsed_ms: float = Field(default=0.0, description="Wall-clock time in milliseconds")
    results: list[BatchWebFetchEntry] = Field(default_factory=list, description="Per-URL results")

    def __str__(self) -> str:
        import json

        return json.dumps(
            {
                "total": self.total,
                "succeeded": self.succeeded,
                "failed": self.failed,
                "session": self.session,
                "elapsed_ms": self.elapsed_ms,
                "results": [r.model_dump() for r in self.results],
            },
            ensure_ascii=False,
        )


# ── Sessions ─────────────────────────────────────────────────────────


class SessionInfo(BaseModel):
    """Summary view of an active web session."""

    id: str = Field(description="Session id")
    created_at: float = Field(description="time.time() when created")
    last_used: float = Field(description="time.time() when last used")
    history_size: int = Field(description="Number of recorded activities")
    is_default: bool = Field(description="True if this is the long-lived default session")
