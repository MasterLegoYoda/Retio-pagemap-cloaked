# PageMap Pi Extension

Read-only web access for [Pi](https://pi.dev) without the MCP server.

This extension registers four custom tools that shell out to the `pagemap` CLI:

| Tool | What it does |
|------|--------------|
| `pagemap_search` | Web search via DuckDuckGo. Returns `{title,url,snippet}`. |
| `pagemap_fetch` | Fetch a URL and return extracted markdown / text / html / json. |
| `pagemap_batch_fetch` | Fetch up to 10 URLs in parallel (max 5 concurrent). |
| `pagemap_sessions` | List or close named web sessions. |

The interactive tools (`get_page_map`, `execute_action`, `fill_form`,
`screenshot`, multi-tab) are MCP-only and are not exposed here. If you need
those, register the PageMap MCP server with your host instead — see
`../../skills/browse-page/SKILL.md` and the top-level `README.md`.

## Install

```bash
# 1. Make sure the pagemap CLI is on PATH
pip install retio-pagemap
cloakbrowser install         # one-time, downloads patched Chromium

# 2. Install extension deps (typebox is the only runtime dep)
cd .pi/extensions/pagemap
npm install

# 3. Symlink into Pi's global extension directory
ln -s "$(pwd)" ~/.pi/agent/extensions/pagemap
```

Or skip the symlink and load it explicitly:

```bash
pi -e /path/to/Retio-pagemap-cloaked/.pi/extensions/pagemap/index.ts
```

After install, the four tool names should appear in Pi's available tools
(alongside the built-in `bash`, `read`, `write`, etc.). No MCP server
process is required.

## Environment overrides

| Var | Default | Purpose |
|-----|---------|---------|
| `PAGEMAP_BIN` | `pagemap` | Path to the CLI binary. |
| `PAGEMAP_CLOAK_PROXY` | (unset) | Forwarded to the CLI for proxy routing. |
| `PAGEMAP_CLOAK_GEOIP` | (unset) | `1` to derive locale/timezone from proxy IP. |
| `PAGEMAP_ALLOW_LOCAL` | (auto) | The extension sets this to `1` automatically for `localhost` / `127.0.0.1` URLs. |

The full set of `PAGEMAP_CLOAK_*` env vars is documented in the top-level
`README.md` and is forwarded to the CLI as-is.

## Why not just `bash`?

A skill that tells the model to run `pagemap fetch <url>` via the built-in
`bash` tool works, but each call is free-form: the model has to remember the
right flags, the JSON shape varies, and large outputs blow up context.

The extension pins the interface with `typebox` schemas so:

- The four tool names live in Pi's system prompt as one-liners (not 18
  MCP tool descriptions).
- Schemas are validated, so `--max-results 99999` fails fast.
- The extension sets `PAGEMAP_ALLOW_LOCAL=1` for localhost URLs
  automatically, which the model would otherwise forget.
