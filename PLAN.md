# CloakBrowser-First Integration

## Summary
- Convert this fork to use CloakBrowser as the only browser launcher while keeping Playwright APIs internally, since CloakBrowser returns Playwright-compatible `Browser`/`BrowserContext` objects.
- Use CloakBrowser features beyond binary substitution: source-level stealth args, humanized interactions, proxy support, GeoIP timezone/locale, WebRTC proxy IP spoofing, extension loading, optional patchright backend, and optional persistent profiles.
- Treat this as an internal deployment: Docker may pre-download/cache the CloakBrowser binary, but note CloakBrowser’s separate binary license before distributing images externally. Sources: [CloakBrowser README](https://github.com/CloakHQ/CloakBrowser), [binary license](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md).

## Key Changes
- Add `cloakbrowser[geoip,patchright]>=0.3.31,<0.4` as a required dependency and remove the project’s Playwright Chromium auto-install path.
- Replace direct `async_playwright().start().chromium.launch(...)` calls in `BrowserSession` and `BrowserPool` with CloakBrowser launch helpers:
  - shared browser mode: `cloakbrowser.launch_async(...)`
  - optional persistent profile mode: `cloakbrowser.launch_persistent_context_async(...)`
- Extend `BrowserConfig` with explicit Cloak options:
  - `proxy`, `geoip`, `timezone`, `cloak_backend`
  - `humanize`, `human_preset`, `human_config`
  - `extension_paths`, `stealth_args`, `extra_args`
  - `persistent_profile`, `profile_root`
- Add CLI/env plumbing:
  - `PAGEMAP_CLOAK_PROXY`
  - `PAGEMAP_CLOAK_GEOIP`
  - `PAGEMAP_CLOAK_TIMEZONE`
  - `PAGEMAP_CLOAK_BACKEND=playwright|patchright`
  - `PAGEMAP_CLOAK_HUMANIZE`
  - `PAGEMAP_CLOAK_HUMAN_PRESET=default|careful`
  - `PAGEMAP_CLOAK_HUMAN_CONFIG_JSON`
  - `PAGEMAP_CLOAK_EXTENSION_PATHS`
  - `PAGEMAP_CLOAK_PERSISTENT`
  - `PAGEMAP_CLOAK_PROFILE_ROOT`
- Keep `--bot-ua` as an explicit compliance mode, but default to CloakBrowser’s normal browser fingerprint behavior.

## Behavior Details
- Disable PageMap’s custom JS stealth bundle by default under CloakBrowser to avoid double-spoofing and detectable injected stealth code; retain an override for debugging.
- Keep PageMap’s security scanner and SSRF route guards. If `patchright` breaks init-script/CDP behavior, scanner setup should fail soft exactly like it does today.
- Update scroll behavior so `humanize=True` uses Playwright mouse wheel input where practical instead of pure `window.scrollBy(...)`; click/type/fill paths can rely on CloakBrowser’s patched Locator/Page methods.
- Persistent profiles are opt-in. In shared pool mode, keep the current single Cloak browser process with isolated contexts. In persistent mode, each session gets its own Cloak persistent context under `profile_root/session_id`, still bounded by the existing pool semaphore.

## Docker
- Replace `playwright install --with-deps chromium` with system dependency installation plus CloakBrowser binary predownload.
- Set internal-deployment defaults in Docker:
  - `CLOAKBROWSER_AUTO_UPDATE=false`
  - pre-run `python -m cloakbrowser install`
  - ensure the cached binary/profile directories are readable by the non-root `pagemap` user.
- Keep stock Playwright as a Python dependency only because CloakBrowser uses the Playwright API underneath.

## Test Plan
- Update unit tests that patch `async_playwright` to patch CloakBrowser launch functions instead.
- Add tests for:
  - `BrowserConfig` Cloak defaults and env parsing
  - launch kwargs passed to `launch_async`
  - proxy/geoip/timezone/humanize/extensions/backend passthrough
  - PageMap JS stealth disabled by default with Cloak
  - persistent profile sessions bypass shared browser startup and close contexts cleanly
  - pool shutdown still closes Cloak-patched browsers without double-stopping Playwright
- Keep live antibot tests optional/marked network-only; do not require downloading CloakBrowser binary in normal unit tests.

## Assumptions
- This fork is for your own/internal use, so CloakBrowser will be required rather than optional.
- Default backend is CloakBrowser’s Playwright backend; `patchright` is exposed but not default because this repo depends on context scripts and CDP for scanner/accessibility behavior.
- Persistent profiles are opt-in because they change resource usage from one shared browser process to one browser profile/process per active session.
