# TODO

## Features

- [x] actully implement the "simple" (no browser automation) http backends. take a look at:
    - https://github.com/refraction-networking/utls
    - https://pypi.org/project/cycletls/
    - https://github.com/lexiforest/curl_cffi
    - https://pypi.org/project/tls-client/

## Implementation notes

`src/pagemap/pipeline/` ships a pluggable pipeline: retrievers
(`pipeline/retriever/` — `cloak` CloakBrowser and `fetch` stealth
HTTP with an `HttpBackend` protocol: `curl_cffi`, `httpx`, and
`urllib` reference implementations), search providers
(`pipeline/retriever/providers/`), and extractors
(`pipeline/extractor/` — `retio`, `pulpie`, `markdown`).  The
`web_fetch` / `batch_web_fetch` `mode="fast"` path now uses this
instead of raising "not yet implemented".  Configuration via
`--retriever` / `--extractor` / `PAGEMAP_RETRIEVER` /
`PAGEMAP_EXTRACTOR`, and `--fast-backend` / `PAGEMAP_FAST_BACKEND`;
install with `pip install 'retio-pagemap[fast]'` to get `curl_cffi`
(preferred for TLS-impersonating fetches).
