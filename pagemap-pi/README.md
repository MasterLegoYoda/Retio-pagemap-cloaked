# PageMap Pi Package

Read-only web access for [Pi](https://pi.dev) via the PageMap CLI. No MCP server required.

## What's included

| Type | Name | Description |
|------|------|-------------|
| Extension | `pagemap-pi-extension` | Registers 4 custom tools: `pagemap_search`, `pagemap_fetch`, `pagemap_batch_fetch`, `pagemap_sessions` |
| Skill | `pagemap-web-fetch` | Read-only workflow: search → fetch → batch fetch with named sessions |
| Skill | `pagemap-browse-page` | Full browser automation path (MCP server required) + reference to the Pi extension |

## Install

### Prerequisites

```bash
# Python package with the `pagemap` CLI
pip install retio-pagemap

# CloakBrowser (patched Chromium for anti-detection)
cloakbrowser install
```

### Global install (all projects)

```bash
pi install ./pagemap-pi
# or from git:
# pi install git:github.com/Retio-ai/Retio-pagemap-cloaked@v1
```

### Project-local install (shared via `.pi/settings.json`)

```bash
pi install -l ./pagemap-pi
```

After install, restart Pi or run `/reload` in the TUI. The four tools will appear alongside the built-ins.

## Tools

| Tool | Description |
|------|-------------|
| `pagemap_search(query, max_results?, recency?, provider?, domain?, use_browser?, session?)` | Web search. Returns `[{title, url, snippet}, ...]`. |
| `pagemap_fetch(url, format?, max_chars?, mode?, session?)` | Fetch a URL. Returns markdown (default), text, html, or JSON. |
| `pagemap_batch_fetch(urls, format?, max_chars?, max_concurrency?, mode?, session?)` | Parallel fetch up to 10 URLs (max 5 concurrent). |
| `pagemap_sessions(action, session_id?)` | List or close web sessions. |

### Search parameters

- `query` (required) — search string
- `max_results` (1-20, default 10)
- `recency` — `day` \| `week` \| `month` \| `year`
- `provider` — `duckduckgo` (default) \| `brave` \| `bing` \| `google` \| `searxng` \| `exa` \| `tavily` \| `firecrawl`
- `domain` — array of domains to include, prefix with `-` to exclude
- `use_browser` — render search page via CloakBrowser (default `false`)
- `session` — session id (`"new"`, `"new:name"`, or existing id)

### Fetch / Batch-fetch parameters

- `url` / `urls` (required)
- `format` — `markdown` (default) \| `text` \| `html` \| `json` (fetch only) / `markdown` \| `text` \| `html` (batch)
- `max_chars` — truncation limit (default 50,000)
- `mode` — `browser` (default, CloakBrowser) \| `fast` (HTTP-only, no JS)
- `max_concurrency` — batch only, 1-5 (default 5)
- `session` — session id

### Session management

```bash
# Create named session
pagemap_search(query="rust async", session="new:rust-research")
# → response includes session="web-xxxxxxxx"

# Reuse session
pagemap_fetch(url="https://blog.rust-lang.org/...", session="web-xxxxxxxx")

# List sessions
pagemap_sessions(action="list")

# Close
pagemap_sessions(action="close", session_id="web-xxxxxxxx")
# Use "default" to reset the default session.
```

## Environment overrides

| Variable | Default | Purpose |
|----------|---------|---------|
| `PAGEMAP_BIN` | `pagemap` | Path to the CLI binary |
| `PAGEMAP_CLOAK_PROXY` | (unset) | Forwarded to CLI for proxy routing |
| `PAGEMAP_CLOAK_GEOIP` | (unset) | `1` to derive locale/timezone from proxy IP |
| `PAGEMAP_ALLOW_LOCAL` | auto | Extension sets `1` automatically for `localhost` / `127.0.0.1` / `[::1]` |

## Examples

```bash
# Look up a library
pagemap_search(query="python asyncio gather", max_results=5)
pagemap_fetch(url="https://docs.python.org/3/library/asyncio-task.html")

# Compare implementations
pagemap_batch_fetch(urls=[
  "https://docs.a.example.com/impl-a",
  "https://docs.b.example.com/impl-b",
], max_concurrency=2)

# Named session for organic traffic shaping
pagemap_search(query="rust async", session="new:rust-research")
pagemap_fetch(url="https://blog.rust-lang.org/...", session="rust-research")

# Fast mode (HTTP-only, no CloakBrowser needed)
pagemap_fetch(url="https://example.com/docs", mode="fast")
pagemap_batch_fetch(urls=["https://a", "https://b"], mode="fast")
```

## Uninstall

```bash
pi remove pagemap-pi-package
# or project-local:
pi remove -l pagemap-pi-package
```

## Update after changes

```bash
# Reinstall (removes then installs)
pi install ./pagemap-pi --force

# Or update in place
pi update --extensions pagemap-pi-package
```

## Project structure

```
pagemap-pi/
├── package.json              # Pi package manifest (pi-package keyword, pi.*)
├── extensions/
│   └── pagemap/
│       ├── package.json      # Extension deps (typebox, pi-coding-agent)
│       └── index.ts          # Extension entry point (4 tools)
└── skills/
    ├── pagemap-web-fetch/
    │   └── SKILL.md          # Read-only workflow docs
    └── pagemap-browse-page/
        └── SKILL.md          # Full browser automation docs
```

## Development

```bash
# From repo root
make pi-install      # Global install
make pi-install-local  # Project-local install
make pi-uninstall    # Uninstall
make pi-update       # Update after code changes
make pi-clean        # Remove node_modules/
```

## License

AGPL-3.0-only — see [LICENSE](../LICENSE) in the main repo.