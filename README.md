<!-- mcp-name: io.github.Retio-ai/pagemap -->

# PageMap

Structured web intelligence for AI agents, built on a configurable two-stage pipeline. Raw HTML (100K+ tokens) becomes structured, AI-readable page maps (2-5K tokens) — a **97% token reduction** — and live browsing runs through a stealth browser stack instead of stock Playwright Chromium.

Derived from [Retio AI's PageMap](https://github.com/Retio-ai/Retio-pagemap) (AGPL-3.0), this project grew well beyond its fork roots:

- **Configurable retrieval** — [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) (patched Chromium with source-level fingerprint patches, proxy-aware locale/timezone, optional humanized input, extension loading, persistent profiles, optional Patchright backend) *or* **stealth HTTP** (`curl_cffi` TLS impersonation — no browser, no JS, cheap and fast)
- **Pluggable extraction** — `retio` (the original full PageMap core) *or* `pulpie` (third-party encoder markdown), plus a bare `markdown` mode
- **18 MCP tools** across two paths — full browser automation (read, click, type, navigate, multi-tab) and read-only web search/fetch with named sessions
- **A Pi package** (`pagemap-pi`) for token-efficient read-only web access without an MCP server

> *"Give your agent eyes and hands on the web."*

[![CI](https://github.com/MasterLegoYoda/Retio-pagemap-cloaked/actions/workflows/ci.yml/badge.svg)](https://github.com/MasterLegoYoda/Retio-pagemap-cloaked/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/retio-pagemap)](https://pypi.org/project/retio-pagemap/)
[![Python](https://img.shields.io/pypi/pyversions/retio-pagemap)](https://pypi.org/project/retio-pagemap/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Docker](https://img.shields.io/docker/v/retio1001/pagemap?label=Docker)](https://hub.docker.com/r/retio1001/pagemap)
[![Awesome MCP Servers](https://img.shields.io/badge/Awesome-MCP%20Servers-fc60a8?logo=awesomelists&logoColor=white)](https://github.com/punkpeye/awesome-mcp-servers)

---

<!-- ============================================================ -->
<!--  HUMAN GUIDE                                                  -->
<!-- ============================================================ -->

## Why PageMap?

Playwright MCP dumps 50-540KB accessibility snapshots per page, overflowing context windows after 2-3 navigations. Firecrawl and Jina convert HTML to markdown — read-only, no interaction.

PageMap gives your agent a **compressed, actionable** view of any web page:

| | PageMap | Playwright MCP | Firecrawl | Jina Reader |
|--|:------:|:---------:|:-----------:|:--------:|
| **Tokens / page** | **2-5K** | 6-50K | 10-50K | 10-50K |
| **Interaction** | **click / type / select / hover** | Raw tree parsing | Read-only | Read-only |
| **Multi-page sessions** | **Unlimited** | Breaks at 2-3 pages | N/A | N/A |
| **Task success (94 tasks)** | **84.7%** | 61.5% | 64.5% | 57.8% |
| **Avg tokens / task** | **2,710** | 13,737 | 13,888 | 11,424 |
| **Cost / 94 tasks** | **$1.06** | $4.09 | $3.98 | $2.26 |

> Benchmarked across 11 e-commerce sites, 94 static tasks, 7 conditions. 4,700+ tests passing.

---

## Quick Start

PageMap uses [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) for live browsing by default. It downloads its patched Chromium binary on first use, or you can preinstall it with `cloakbrowser install`.

### Install

```bash
pip install retio-pagemap
```

### MCP Client Config

Add to Claude Code, Cursor, Windsurf, or Claude Desktop:

```json
{
  "mcpServers": {
    "pagemap": {
      "command": "uvx",
      "args": ["retio-pagemap"]
    }
  }
}
```

> **Claude Desktop (macOS)**: Use the absolute path to `uvx` — run `which uvx` (e.g. `/opt/homebrew/bin/uvx`).

> **VS Code (Copilot)**: Use `"servers"` instead of `"mcpServers"` in `.vscode/mcp.json`.

### Docker

```bash
docker run -p 8000:8000 retio1001/pagemap --transport http
```

---

## Features

### 18 MCP Tools — Read + Interact

18 tools cover the full browsing workflow across two complementary paths:

- **Browser automation** — click buttons, fill forms, select options, manage tabs, navigate across pages:

  `get_page_map` · `execute_action` · `fill_form` · `scroll_page` · `wait_for` · `take_screenshot` · `get_page_state` · `navigate_back` · `batch_get_page_map` · `open_tab` · `switch_tab` · `list_tabs` · `close_tab`

- **Web fetch (read-only)** — search and fetch content as clean markdown, no refs or interaction needed:

  `web_search` · `web_fetch` · `batch_web_fetch` · `web_list_sessions` · `web_close_session`

### 16 Page Types, Auto-Detected

PageMap automatically classifies pages and applies optimized extraction for each type:

`product_detail` · `listing` · `search_results` · `article` · `news` · `video` · `login` · `form` · `checkout` · `dashboard` · `help_faq` · `settings` · `error` · `documentation` · `landing` · `blocked`

### E-Commerce Deep Coverage

Built-in support for **30+ major e-commerce sites** across 4 tiers:

- **Global mega-platforms** — Amazon, eBay, AliExpress, SHEIN, Walmart, Rakuten
- **Global fashion** — Zara, H&M, Nike, Uniqlo, ASOS, Zalando, SSENSE, Farfetch, COS
- **Korea** — Coupang, Naver Shopping, Musinsa, 29CM, W Concept, SSG, 11st
- **Japan/China** — ZOZO, Tmall, JD.com, Taobao

Structured extraction of prices, options (size/color), ratings, availability — with automatic cookie consent handling and login barrier detection.

### Smart Recovery

PageMap detects problems and tells your agent what to do:

- **Barrier detection** — Login required? Bot blocked? Out of stock? Age verification? Popup overlay? PageMap adds a `barrier` field with the diagnosis and suggested next steps
- **Cookie consent auto-dismiss** — 7 CMP providers auto-detected (Cookiebot, OneTrust, TrustArc, Didomi, Quantcast, Usercentrics, generic fallback). 5-tier dismiss cascade: CMP JS API → Reject → Accept → Dismiss → Close symbol. GDPR reject-first default policy
- **Popup overlay detection** — AX tree `role="dialog"` + HTML regex 2-phase detection. Promotional popups (newsletter, exit-intent) auto-dismissed
- **Bot detection awareness** — Detects Cloudflare, Turnstile, reCAPTCHA, hCaptcha, and Akamai. Reports the provider and suggests wait/retry strategies
- **Stale ref recovery** — When DOM changes invalidate refs, PageMap returns clear guidance to re-fetch

### Content Intelligence

- **8 JSON-LD schemas** — Product, NewsArticle, VideoObject, FAQPage, Event, LocalBusiness, BreadcrumbList, and ItemList
- **Metadata extraction** — Prices, ratings, reviews, descriptions, images from structured data and DOM fallbacks
- **2-layer caching** — Cache hit (~10ms), content refresh (~500ms), full rebuild (~1.5s). Diff-based updates for unchanged sections
- **Delta evidence packet output** - Optional `to_delta_packet()` serializer emits digest-bound evidence units, claim candidates, provenance, and authority flags for downstream memory/review systems without changing the default MCP output

### Configurable Pipeline

PageMap is a pluggable two-stage pipeline: a **retriever** fetches the page, an **extractor** turns the raw HTML into clean, LLM-readable data. Pick the pair at startup with `--retriever` / `--extractor`, or the `PAGEMAP_RETRIEVER` / `PAGEMAP_EXTRACTOR` env vars (resolution is CLI > env > default):

| Knob | Choices | Default |
|---|---|---|
| `--retriever` | `cloak` (CloakBrowser), `fetch` (stealth HTTP), `auto` | `cloak` |
| `--extractor` | `retio` (full PageMap), `pulpie` (encoder markdown, opt-in), `markdown` (BeautifulSoup), `auto` | `retio` |

**Retrievers** — how the page is obtained:

| Retriever | Description |
|---|---|
| `cloak` | CloakBrowser patched Chromium: full JavaScript, anti-detection fingerprints, session continuity. Default. |
| `fetch` | **Stealth HTTP** — `curl_cffi` TLS impersonation (falls back to `httpx` / `urllib`). No browser, no JS: cheap and fast, ideal for static docs, articles, and APIs. |
| `auto` | First available: `cloak` → `fetch`. |

**Extractors** — how the raw HTML becomes LLM-readable data:

| Extractor | MARKDOWN | INTERACTABLES | FORMS | PAGE_TYPE | SCHEMA |
|---|:-:|:-:|:-:|:-:|:-:|
| `retio`     | ✓ | ✓ | ✓ | ✓ | ✓ |
| `pulpie`    | ✓ |   |   |   |   |
| `markdown`  | ✓ |   |   |   |   |

`retio` is the original PageMap core — everything `get_page_map` needs. `pulpie` is a third-party encoder-based markdown extractor (`pip install 'retio-pagemap[pulpie]'`). `markdown` is a thin BeautifulSoup markdown adapter. `auto` picks the most capable available extractor (`retio` → `pulpie` → `markdown`).

**Capability rules:** `get_page_map` requires INTERACTABLES — with `--extractor pulpie` it returns a clear `MissingCapability` error pointing you at `--extractor retio`. `web_fetch` works with any extractor (it only needs MARKDOWN).

Related knobs: `--fast-backend` / `PAGEMAP_FAST_BACKEND` picks the HTTP backend used by `fetch` (`auto` = `curl_cffi` → `httpx` → `urllib`); `PAGEMAP_SEARCH_PROVIDER` sets the default search provider (`duckduckgo`, `brave`, `bing`, `google`, `searxng`, `exa`, `tavily`, `firecrawl`).

```bash
# Cheaper / markdown-only mode (no browser, no JS):
retio-pagemap --retriever fetch --extractor markdown

# Encoder-based extraction (needs the pulpie optional dep):
pip install 'retio-pagemap[pulpie]'
retio-pagemap --extractor pulpie
```

### 10 Languages

Locale auto-detected from URL. Token budgets adjusted for CJK scripts.

| Language | Locale | Language | Locale |
|----------|:------:|----------|:------:|
| English | `en` | Chinese | `zh` |
| Korean | `ko` | Spanish | `es` |
| Japanese | `ja` | Italian | `it` |
| French | `fr` | Portuguese | `pt` |
| German | `de` | Dutch | `nl` |

---

## Deployment

### Local (STDIO)

Default mode. Runs as a local MCP server — no server setup needed.

```bash
retio-pagemap
```

### Docker

```bash
docker run -p 8000:8000 retio1001/pagemap --transport http
```

Multi-architecture images (amd64/arm64) available on [Docker Hub](https://hub.docker.com/r/retio1001/pagemap) and GitHub Container Registry.

### Pi (no MCP)

A token-efficient [Pi](https://pi.dev) package lives at
[`pagemap-pi/`](pagemap-pi/README.md). It ships an extension that
registers four read-only tools (`pagemap_search`, `pagemap_fetch`,
`pagemap_batch_fetch`, `pagemap_sessions`) that shell out to the
`pagemap` CLI, plus the `pagemap-web-fetch` and `pagemap-browse-page`
skills. No MCP server, no 18-tool context blast.

```bash
make pi-install                  # npm install + global pi install
make pi-install-local            # project-local install (.pi/settings.json)
make pi-update                   # re-install after code changes
make pi-uninstall                # remove the package
make pi-clean                    # remove node_modules/
# or, without make:
bash scripts/install-pi-package.sh
bash scripts/uninstall-pi-package.sh
```

After `pi-install`, restart Pi (or run `/reload` in the TUI). The
four tools should appear alongside the built-ins.

The interactive tools (`get_page_map` / `execute_action` / `fill_form` /
screenshots / multi-tab) are MCP-only and are not exposed by the
extension. Use the MCP server for those flows.

See [`pagemap-pi/README.md`](pagemap-pi/README.md) and `skills/web-fetch/SKILL.md`
for full details.

---

## Python API

```python
import asyncio
from pagemap.browser_session import BrowserSession
from pagemap.delta_serializer import to_delta_packet
from pagemap.page_map_builder import build_page_map_live
from pagemap.serializer import to_agent_prompt, to_json

async def main():
    async with BrowserSession() as session:
        page_map = await build_page_map_live(session, "https://example.com/product/123")
        print(to_agent_prompt(page_map))   # Agent-optimized text format
        print(to_json(page_map))           # Structured JSON
        print(to_delta_packet(page_map))   # Digest-bound evidence packet
        print(page_map.page_type)          # "product_detail"
        print(page_map.interactables)      # [Interactable(ref=1, role="button", ...)]
        print(page_map.metadata)           # {"name": "...", "price": "..."}

asyncio.run(main())
```

For offline processing (no browser):

```python
from pagemap.page_map_builder import build_page_map_offline

page_map = build_page_map_offline(open("page.html").read(), url="https://example.com/product/123")
```

---

## Security

PageMap treats all web content as untrusted input:

- **SSRF defense** — Multi-layer protection against server-side request forgery
- **Prompt injection defense** — Content boundaries, role-prefix stripping, suspicious content flagging
- **robots.txt compliance** — RFC 9309 compliant. `--ignore-robots` opt-out flag
- **Resource guards** — DOM node limit, HTML size limit, response size limit
- **Session isolation** — Each session has independent cookies and storage, automatically cleaned up

**Local development**: Private IPs are blocked by default. Use `--allow-local` or `PAGEMAP_ALLOW_LOCAL=1`.

### Disclaimer

Users are responsible for complying with the terms of service of target websites and all applicable laws when using PageMap.

---

## Troubleshooting

**"spawn uvx ENOENT" (Claude Desktop on macOS)** — Claude Desktop does not inherit your shell PATH. Run `which uvx` and use the absolute path in your config.

**First page takes a long time** — CloakBrowser binary download and Chromium cold start can take ~10-30s on first navigation. Subsequent pages load in 1-3 seconds.

**Localhost blocked** — Use `--allow-local` flag or set `PAGEMAP_ALLOW_LOCAL=1`.

**CloakBrowser binary not found** — Run `pip install retio-pagemap && cloakbrowser install` to install manually.

**CloakBrowser options** — Live browsing runs through CloakBrowser by default. Useful knobs:
`PAGEMAP_CLOAK_PROXY`, `PAGEMAP_CLOAK_GEOIP=1`, `PAGEMAP_CLOAK_TIMEZONE`,
`PAGEMAP_CLOAK_LOCALE`, `PAGEMAP_CLOAK_BACKEND=patchright`,
`PAGEMAP_CLOAK_HUMANIZE=1`, `PAGEMAP_CLOAK_EXTENSION_PATHS`, and
`PAGEMAP_CLOAK_PERSISTENT=1`.

**Pipeline retriever / extractor** — See [Configurable Pipeline](#configurable-pipeline)
above for the full retriever/extractor matrix, capability rules, and examples.

---

## Requirements

- Python 3.11+
- CloakBrowser patched Chromium, installed automatically on first use or manually with `cloakbrowser install`

## Community

Have a question or idea? Join the conversation in [GitHub Discussions](https://github.com/MasterLegoYoda/Retio-pagemap-cloaked/discussions).

## Development

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/MasterLegoYoda/Retio-pagemap-cloaked?quickstart=1)

```bash
git clone https://github.com/MasterLegoYoda/Retio-pagemap-cloaked.git
cd Retio-pagemap-cloaked
uv sync --group dev
cloakbrowser install
uv run pytest --tb=short -q
```

## Pricing

**Local (STDIO)** — Free forever. Self-hosted, open source under AGPL-3.0.

**Cloud API** — Hosted multi-tenant server with auth, rate limiting, and credit-based billing. Contact **retio1001@retio.ai** for access.

## License

AGPL-3.0-only — see [LICENSE](LICENSE) for the full text.

For commercial licensing options, contact **retio1001@retio.ai**.

---

<!-- ============================================================ -->
<!--  AGENT REFERENCE                                              -->
<!-- ============================================================ -->

## For Agents

*This section is written for AI agents using PageMap as an MCP tool.*

### Tools

Two complementary paths — use the **web-fetch tools for read-only lookups** (docs, articles, any "just give me the content" task), and the **browser-automation tools to interact with a page** (click, type, form-fill, multi-tab flows).

| Tool | When to use |
|------|-------------|
| `web_search` | **Read-only lookups start here.** Search the web, pick a URL, then `web_fetch`. |
| `web_fetch` | Fetch a URL as markdown/text/html/JSON. `mode="fast"` uses stealth HTTP (no browser). |
| `batch_web_fetch` | Fetch up to 10 URLs in parallel. Use for comparison tasks. |
| `web_list_sessions` | List active web sessions (default, named, or generated). |
| `web_close_session` | Close a web session, or reset the `default` session. |
| `get_page_map` | **Interaction starts here.** Navigate to a URL and get a full structured map with numbered refs. |
| `execute_action` | Click, type, select, or hover using a ref number from the last `get_page_map`. |
| `fill_form` | Fill multiple form fields in one call. More efficient than sequential `execute_action` calls. |
| `get_page_state` | Check current URL and title without a full rebuild. Use after actions that may navigate. |
| `scroll_page` | Scroll to reveal lazy-loaded content before calling `get_page_map` again. |
| `wait_for` | Wait for dynamic content to appear (e.g. after a search or form submit). |
| `take_screenshot` | Capture the visual state when the PageMap alone is ambiguous. |
| `navigate_back` | Go back one step in browser history. |
| `open_tab` | Open a new browser tab and navigate to a URL. |
| `switch_tab` | Switch to a different open tab by index. |
| `list_tabs` | List all open tabs with their URLs and titles. |
| `close_tab` | Close a tab by index. |
| `batch_get_page_map` | Fetch structured Page Maps for multiple URLs in parallel. |

### Output Format

```yaml
URL: https://example.com/product/123
Title: Product Name
Type: product_detail          # auto-detected page type

## Actions
[1] button: Add to cart (click)
[2] select: Size (select) — options: S, M, L, XL
[3] link: See all reviews (click)
...

## Info
Price: $49.99
Rating: 4.5 / 5 (128 reviews)
Description: ...

## Images
  [1] https://cdn.example.com/product.jpg

## Meta
Tokens: ~1,800 | Interactables: 24 | Generation: 380ms
```

- **`## Actions`** — Every interactive element on the page with a stable `ref` number.
- **`## Info`** — Key page content extracted from HTML: prices, titles, ratings, descriptions.
- **`## Images`** — Product/content image URLs.
- **`## Meta`** — Token count, interactable count, generation time.

### Barrier Detection

When PageMap encounters a page-level obstacle, it includes a `barrier` field in the response:

```yaml
State:
  barrier: login_required
  barrier_hint: "Login form detected with email + password fields. Use fill_form to authenticate."
```

Possible barriers: `cookie_consent`, `login_required`, `bot_blocked`, `out_of_stock`, `empty_results`, `error_page`, `age_verification`, `region_restricted`, `popup_overlay`.

**When you see a barrier:** follow the `barrier_hint` guidance. For `bot_blocked`, wait and retry. For `login_required`, use `fill_form` with credentials.

### Ref Lifecycle

Refs are assigned by `get_page_map` and remain valid until the page state changes.

**Refs are invalidated when:**
- The page navigates to a new URL
- A DOM mutation occurs (modal opens, SPA navigation, accordion toggles)
- `execute_action` causes a page-level change

**When you get a stale ref error:** call `get_page_map` again to get fresh refs before retrying.

### Token Budget Behavior

When a page exceeds the token budget, content is pruned in this order:
1. Navigation menus, footers, sidebars removed first
2. Secondary body content trimmed
3. `## Actions` and `## Info` are always preserved

If key content seems missing, try `scroll_page` to load lazy content, then `get_page_map` again.

### Recommended Workflow

```
1. get_page_map(url)          → read Actions + Info, pick refs
2. execute_action(ref, ...)   → interact
3. get_page_state()           → confirm navigation occurred
4. get_page_map(new_url)      → get fresh refs for next step
```

For pages with dynamic content (search results, filters):
```
1. get_page_map(url)
2. execute_action(ref, "click")    → trigger search/filter
3. wait_for(text="results")        → wait for content
4. get_page_map(url)               → get updated map
```

### Known Limitations

- **Login-gated pages** — PageMap does not manage sessions or cookies. Authentication must be handled externally.
- **Heavy bot detection** (Cloudflare, Akamai) — May block automated access. PageMap detects the provider and suggests strategies, but cannot bypass active bot mitigation.
- **Private network access** — Blocked by default. Requires `--allow-local` flag.
- **iframes** — Cross-origin iframes are not accessible due to browser security policies.

---

*PageMap — Structured Web Intelligence for the Agent Era.*
