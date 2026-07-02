# Example invocations

These are the tool calls a Pi agent would make. They mirror the `pagemap`
CLI surface but go through the extension.

## Look up a library

```
1. pagemap_search(query="python asyncio gather", max_results=5)
   → [{title: "asyncio — Asynchronous I/O", url: "https://docs.python.org/3/library/asyncio.html", ...}, ...]

2. pagemap_fetch(url="https://docs.python.org/3/library/asyncio-task.html")
   → markdown of the asyncio task docs
```

## Compare two implementations

```
pagemap_batch_fetch(urls=[
  "https://docs.a.example.com/impl-a",
  "https://docs.b.example.com/impl-b",
], max_concurrency=2)
```

## Same-session continuity (organic-looking traffic)

```
pagemap_search(query="rust async", session="new:rust-research")
  → response returns session="web-xxxxxxxx"

pagemap_fetch(url="https://blog.rust-lang.org/...", session="web-xxxxxxxx")

pagemap_sessions(action="list")
  → shows the active session

pagemap_sessions(action="close", session_id="web-xxxxxxxx")
```

## Read a single article (markdown)

```
pagemap_fetch(url="https://example.com/blog/post", format="markdown", max_chars=20000)
```

## Capped parallel reads

```
pagemap_batch_fetch(
  urls=["https://a", "https://b", "https://c", "https://d"],
  max_concurrency=2,
)
```

## Local development

Localhost URLs work without flags — the extension sets
`PAGEMAP_ALLOW_LOCAL=1` automatically when it detects
`localhost` / `127.0.0.1` / `[::1]`:

```
pagemap_fetch(url="http://localhost:8000/docs")
```
