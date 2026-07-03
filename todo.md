# TODO

## Features

- [x] actully implement the "simple" (no browser automation) http backends. take a look at:
    - https://github.com/refraction-networking/utls
    - https://pypi.org/project/cycletls/
    - https://github.com/lexiforest/curl_cffi
    - https://pypi.org/project/tls-client/

## Implementation notes

`pagemap/web_fetch/http/` ships a pluggable `HttpBackend` protocol with
`curl_cffi`, `httpx`, and `urllib` reference implementations.  The
`web_fetch` / `batch_web_fetch` `mode="fast"` path now uses this
instead of raising "not yet implemented".  Configuration via
`--fast-backend` / `PAGEMAP_FAST_BACKEND`; install with
`pip install 'retio-pagemap[fast]'` to get `curl_cffi` (preferred
for TLS-impersonating fetches).
