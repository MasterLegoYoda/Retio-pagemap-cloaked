"""HTML extraction and content truncation for the web fetch layer.

Browser-based ``web_fetch`` obtains raw HTML via Playwright/CloakBrowser and
converts it to a model-friendly format here. The default is markdown so the
returned text is agent-readable and stays small.

The implementation is intentionally lightweight: no JS execution, no
readability scoring, no network calls. It strips obviously noisy elements
(``<script>``, ``<style>``, ``<nav>``, ``<footer>``, ``<aside>``, etc.),
turns a few block tags into markdown line breaks, and otherwise preserves
the visible text.

When the extracted text exceeds ``max_chars``, the body is truncated and
the un-truncated content is written to a temp file (spillover path) so the
agent can read it on demand.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from .errors import ExtractionError
from .models import FetchFormat

__all__ = [
    "ExtractedDocument",
    "MAX_DEFAULT_CHARS",
    "extract",
    "spillover_path_for",
]

MAX_DEFAULT_CHARS = 50_000

_NOISE_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
        "canvas",
        "video",
        "audio",
        "source",
        "track",
        "object",
        "embed",
        "form",
        "input",
        "button",
        "select",
        "textarea",
        "link",
        "meta",
    }
)

_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

# Templates for the spillover dir; safe across platforms.
_TMP_DIR_DEFAULT = "/tmp"


@dataclass
class ExtractedDocument:
    """Result of running ``extract`` on a raw HTML payload."""

    title: str | None
    content: str
    content_length: int
    truncated: bool
    full_output_path: str | None
    warnings: list[str]


def _tmp_dir() -> str:
    return os.environ.get("PAGEMAP_WEB_TMP_DIR", _TMP_DIR_DEFAULT)


def spillover_path_for(url: str, fmt: FetchFormat) -> str:
    """Return a stable, collision-resistant spillover file path."""
    digest = hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()[:16]
    suffix = {
        FetchFormat.markdown: ".md",
        FetchFormat.text: ".txt",
        FetchFormat.html: ".html",
        FetchFormat.json: ".json",
    }.get(fmt, ".txt")
    return os.path.join(_tmp_dir(), f"pagemap-web-fetch-{digest}{suffix}")


def _strip_noise(soup: BeautifulSoup) -> list[str]:
    """Remove noisy subtrees and return the list of warnings (if any)."""
    warnings: list[str] = []
    for tag in soup.find_all(lambda t: isinstance(t, Tag) and t.name in _NOISE_TAGS):
        try:
            tag.decompose()
        except Exception:  # nosec B110 — best effort
            warnings.append(f"failed to remove <{tag.name}>")
    return warnings


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def _ensure_inline_space(prev: str, nxt: str) -> str:
    """Return ``nxt`` with a leading space if ``prev`` and ``nxt`` would otherwise
    smash word characters together (e.g. ``Hello`` + ``**world**``)."""
    if not prev or not nxt:
        return nxt
    if prev[-1].isspace() or nxt[0].isspace():
        return nxt
    # Punctuation: never insert a space.
    if prev[-1] in "(*[`{<>\"'":
        return nxt
    if nxt[0] in ".,;:!?)]}\"'>":
        return nxt
    return " " + nxt


def _node_to_markdown(node: Any, *, list_stack: list[str]) -> str:
    """Render a BeautifulSoup node as markdown.

    ``list_stack`` tracks the ordered/unordered list context at each
    nesting level so nested lists stay sane.
    """
    if isinstance(node, NavigableString):
        # Do NOT collapse here; the parent render pass does that, and
        # collapsing per-node destroys inter-word spacing.
        return str(node)

    if not isinstance(node, Tag):
        return ""

    name = (node.name or "").lower()

    if name in _HEADING_TAGS:
        level = _HEADING_TAGS[name]
        inner = _render_children(node, list_stack=list_stack)
        inner = _collapse_whitespace(inner)
        if not inner:
            return ""
        return f"\n\n{'#' * level} {inner}\n\n"

    if name == "p":
        inner = _render_children(node, list_stack=list_stack)
        inner = _collapse_whitespace(inner)
        if not inner:
            return ""
        return f"\n\n{inner}\n\n"

    if name == "br":
        return "  \n"

    if name in ("strong", "b"):
        inner = _render_children(node, list_stack=list_stack).strip()
        return f"**{inner}**" if inner else ""

    if name in ("em", "i"):
        inner = _render_children(node, list_stack=list_stack).strip()
        return f"*{inner}*" if inner else ""

    if name == "code":
        inner = _render_children(node, list_stack=list_stack).strip()
        return f"`{inner}`" if inner else ""

    if name == "pre":
        # Pre is rendered as a fenced block; find any nested <code> or fall back
        # to the raw text.
        code = node.find("code")
        if isinstance(code, Tag):
            text = code.get_text()
        else:
            text = node.get_text()
        text = text.strip("\n")
        return f"\n\n```\n{text}\n```\n\n"

    if name == "blockquote":
        inner = _render_children(node, list_stack=list_stack)
        inner = _collapse_whitespace(inner)
        if not inner:
            return ""
        quoted = "\n".join(f"> {line}" for line in inner.splitlines() if line)
        return f"\n\n{quoted}\n\n"

    if name == "a":
        inner = _render_children(node, list_stack=list_stack).strip()
        href = node.get("href", "").strip()
        if not inner:
            return ""
        if href and not href.lower().startswith(("javascript:", "data:", "mailto:")):
            return f"[{inner}]({href})"
        return inner

    if name == "img":
        alt = node.get("alt", "").strip() or "(image)"
        src = node.get("src", "").strip()
        if src:
            return f"![{alt}]({src})"
        return f"![{alt}]"

    if name in ("ul", "ol"):
        ordered = name == "ol"
        list_stack.append("ol" if ordered else "ul")
        try:
            items: list[str] = []
            for i, li in enumerate(node.find_all("li", recursive=False), start=1):
                marker = f"{i}." if ordered else "-"
                inner = _render_children(li, list_stack=list_stack)
                inner = _collapse_whitespace(inner)
                if not inner:
                    continue
                items.append(f"{marker} {inner}")
            if not items:
                return ""
            return "\n\n" + "\n".join(items) + "\n\n"
        finally:
            list_stack.pop()

    if name in ("table", "tr", "td", "th", "thead", "tbody", "tfoot"):
        return _render_table(node, list_stack=list_stack)

    if name == "hr":
        return "\n\n---\n\n"

    # Fallback: render children.
    return _render_children(node, list_stack=list_stack)


def _render_table(node: Tag, *, list_stack: list[str]) -> str:
    """Render a simple table as a markdown table (best-effort)."""
    if node.name == "tr":
        cells = [
            _collapse_whitespace(_render_children(c, list_stack=list_stack)).replace("|", "\\|")
            for c in node.find_all(["td", "th"], recursive=False)
        ]
        if not cells:
            return ""
        return "| " + " | ".join(cells) + " |"

    rows: list[str] = []
    header_done = False
    for tr in node.find_all("tr"):
        cells = [
            _collapse_whitespace(_render_children(c, list_stack=list_stack)).replace("|", "\\|")
            for c in tr.find_all(["td", "th"], recursive=False)
        ]
        if not cells:
            continue
        rows.append("| " + " | ".join(cells) + " |")
        if not header_done:
            rows.append("| " + " | ".join("---" for _ in cells) + " |")
            header_done = True
    if not rows:
        return ""
    return "\n\n" + "\n".join(rows) + "\n\n"


def _render_children(node: Any, *, list_stack: list[str]) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, Tag):
            chunk = _node_to_markdown(child, list_stack=list_stack)
        elif isinstance(child, NavigableString):
            chunk = str(child)
        else:
            continue
        if not chunk:
            continue
        # Insert a single space when an inline boundary would otherwise glue
        # two word-tokens together (e.g. "Hello " + "**world**").
        if parts and not chunk.startswith(("\n", " ", "\t")):
            parts.append(_ensure_inline_space(parts[-1], chunk))
        else:
            parts.append(chunk)
    return "".join(parts)


def _to_markdown(soup: BeautifulSoup) -> str:
    body = soup.body or soup
    list_stack: list[str] = []
    parts: list[str] = []
    for child in body.children:
        if isinstance(child, Tag):
            parts.append(_node_to_markdown(child, list_stack=list_stack))
        elif isinstance(child, NavigableString):
            text = _collapse_whitespace(str(child))
            if text:
                parts.append(text)
    text = "".join(parts)
    # Collapse runs of 3+ blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _to_text(soup: BeautifulSoup) -> str:
    body = soup.body or soup
    return re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True)).strip()


def _truncate(content: str, max_chars: int, *, url: str, fmt: FetchFormat) -> tuple[str, bool, str | None]:
    if max_chars <= 0 or len(content) <= max_chars:
        return content, False, None
    head = content[:max_chars]
    path = spillover_path_for(url, fmt)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        path = None
    return head, True, path


def extract(
    *,
    raw_html: str,
    url: str,
    fmt: FetchFormat,
    max_chars: int = MAX_DEFAULT_CHARS,
) -> ExtractedDocument:
    """Extract title and content from a raw HTML payload.

    Args:
        raw_html: The page HTML as returned by the browser.
        url: Source URL (used to build the spillover path).
        fmt: Output format. ``markdown`` / ``text`` parse the HTML;
            ``html`` returns the (de-noised) source HTML; ``json`` returns
            a minimal structured document.
        max_chars: Truncation limit. Pass ``<=0`` to disable.
    """
    if raw_html is None:
        raise ExtractionError("No HTML payload to extract from.")

    if fmt == FetchFormat.html:
        content = raw_html
        title: str | None = None
        warnings: list[str] = []
        try:
            soup = BeautifulSoup(raw_html, "lxml")
            warnings = _strip_noise(soup)
            if soup.title and soup.title.string:
                title = _collapse_whitespace(soup.title.string)
            content = str(soup)
        except Exception as exc:  # nosec B110
            warnings.append(f"html re-parse failed: {exc}")
        content, truncated, path = _truncate(content, max_chars, url=url, fmt=fmt)
        return ExtractedDocument(
            title=title,
            content=content,
            content_length=len(content),
            truncated=truncated,
            full_output_path=path,
            warnings=warnings,
        )

    if fmt == FetchFormat.json:
        title = None
        try:
            soup = BeautifulSoup(raw_html, "lxml")
            if soup.title and soup.title.string:
                title = _collapse_whitespace(soup.title.string)
        except Exception:
            title = None
        import json

        body = ExtractedDocument(
            title=title,
            content="",
            content_length=0,
            truncated=False,
            full_output_path=None,
            warnings=[],
        )
        del body  # placeholder; we serialize below

        payload = {
            "url": url,
            "title": title,
            "format": "json",
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        text, truncated, path = _truncate(text, max_chars, url=url, fmt=fmt)
        return ExtractedDocument(
            title=title,
            content=text,
            content_length=len(text),
            truncated=truncated,
            full_output_path=path,
            warnings=[],
        )

    # markdown / text path
    try:
        soup = BeautifulSoup(raw_html, "lxml")
    except Exception as exc:
        raise ExtractionError(f"Failed to parse HTML: {exc}") from exc

    warnings = _strip_noise(soup)
    title = None
    if soup.title and soup.title.string:
        title = _collapse_whitespace(soup.title.string)

    if fmt == FetchFormat.markdown:
        content = _to_markdown(soup)
    else:
        content = _to_text(soup)

    # Drop escape artifacts left from the BeautifulSoup default.
    content = html.unescape(content)
    content, truncated, path = _truncate(content, max_chars, url=url, fmt=fmt)
    return ExtractedDocument(
        title=title,
        content=content,
        content_length=len(content),
        truncated=truncated,
        full_output_path=path,
        warnings=warnings,
    )
