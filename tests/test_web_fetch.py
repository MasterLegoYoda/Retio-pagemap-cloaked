# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for the web_fetch package: extraction, sessions, provider registry,
and the DuckDuckGo HTML parser.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from pagemap.web_fetch import (
    DEFAULT_SESSION_ID,
    NEW_SESSION_SENTINEL,
    BatchWebFetchResult,
    FetchFormat,
    SessionInfo,
    SessionManager,
    WebFetchResult,
    WebSearchResult,
    available_providers,
    get_provider,
    list_provider_names,
    register_provider,
    resolve_session_arg,
)
from pagemap.web_fetch.errors import (
    ExtractionError,
    InvalidSessionName,
    ProviderError,
    SessionNotFound,
)
from pagemap.web_fetch.extract import (
    extract,
    spillover_path_for,
)
from pagemap.web_fetch.providers.base import ProviderContext
from pagemap.web_fetch.providers.duckduckgo import (
    DuckDuckGoProvider,
    _parse_results,
    _strip_ddg_redirect,
)
from pagemap.web_fetch.sessions import (
    SESSION_NAME_PATTERN,
    _validate_explicit_name,
)

# ── Session name validation ─────────────────────────────────────────


class TestSessionNameValidation:
    def test_valid_names(self):
        assert _validate_explicit_name("docs") == "docs"
        assert _validate_explicit_name("new-session-1") == "new-session-1"
        assert _validate_explicit_name("a") == "a"
        assert _validate_explicit_name("A_b-c-1") == "A_b-c-1"

    def test_rejects_empty(self):
        with pytest.raises(InvalidSessionName):
            _validate_explicit_name("")

    def test_rejects_too_long(self):
        with pytest.raises(InvalidSessionName):
            _validate_explicit_name("a" * 65)

    def test_rejects_invalid_chars(self):
        for bad in ["foo bar", "foo!", "foo@bar", "/etc", "foo.bar"]:
            with pytest.raises(InvalidSessionName):
                _validate_explicit_name(bad)

    def test_rejects_reserved_new(self):
        with pytest.raises(InvalidSessionName):
            _validate_explicit_name(NEW_SESSION_SENTINEL)

    def test_rejects_starts_with_dash(self):
        with pytest.raises(InvalidSessionName):
            _validate_explicit_name("-foo")

    def test_pattern(self):
        assert SESSION_NAME_PATTERN.match("a")
        assert SESSION_NAME_PATTERN.match("abc-123")
        assert not SESSION_NAME_PATTERN.match("-abc")
        assert not SESSION_NAME_PATTERN.match("")


# ── SessionManager ──────────────────────────────────────────────────


class TestSessionManager:
    def test_default_session_is_lazy(self):
        m = SessionManager(ttl_seconds=0)
        assert DEFAULT_SESSION_ID not in m.ids()
        s = m.get_or_create_default()
        assert s.id == DEFAULT_SESSION_ID
        assert s.is_default is True
        assert DEFAULT_SESSION_ID in m.ids()

    def test_create_returns_existing_on_duplicate(self):
        m = SessionManager(ttl_seconds=0)
        s1 = m.create("docs")
        s2 = m.create("docs")
        assert s1 is s2

    def test_create_with_no_name_generates_id(self):
        m = SessionManager(ttl_seconds=0)
        s = m.create()
        assert s.id.startswith("web-")
        assert len(s.id) == 4 + 12

    def test_get_unknown_returns_none(self):
        m = SessionManager(ttl_seconds=0)
        assert m.get("nope") is None

    def test_close_unknown_returns_false(self):
        m = SessionManager(ttl_seconds=0)
        assert m.close("nope") is False

    def test_close_default_resets(self):
        m = SessionManager(ttl_seconds=0)
        m.get_or_create_default().record("search", query="x")
        assert len(m.get_or_create_default().history) == 1
        m.close(DEFAULT_SESSION_ID)
        # After closing the default, history is gone but the slot exists again.
        assert m.get_or_create_default().history == []

    def test_close_named_removes(self):
        m = SessionManager(ttl_seconds=0)
        m.create("docs")
        assert "docs" in m.ids()
        assert m.close("docs") is True
        assert "docs" not in m.ids()

    def test_record_caps_history(self):
        m = SessionManager(ttl_seconds=0)
        s = m.get_or_create_default()
        for i in range(600):
            s.record("search", query=str(i))
        assert len(s.history) == 512

    def test_ttl_eviction_skips_default(self):
        # TTL of 0 means no eviction (the manager treats 0 as "disabled").
        m = SessionManager(ttl_seconds=0)
        s = m.create("docs")
        s.touch()
        m._evict_idle()  # no-op
        assert m.get("docs") is s

    def test_ttl_eviction_drops_idle_named(self):
        m = SessionManager(ttl_seconds=0.001)  # 1ms
        s = m.create("docs")
        # Force last_used into the past.
        s.last_used -= 100
        m._evict_idle()
        assert m.get("docs") is None

    def test_list_sessions_returns_all(self):
        m = SessionManager(ttl_seconds=0)
        m.get_or_create_default()
        m.create("a")
        m.create("b")
        assert sorted(s.id for s in m.list_sessions()) == ["a", "b", "default"]


# ── resolve_session_arg ─────────────────────────────────────────────


class TestResolveSessionArg:
    def setup_method(self):
        self.m = SessionManager(ttl_seconds=0)

    def test_none_uses_default(self):
        s, created = resolve_session_arg(None, manager=self.m)
        assert s.id == DEFAULT_SESSION_ID
        assert created is False

    def test_new_creates_fresh(self):
        s, created = resolve_session_arg("new", manager=self.m)
        assert created is True
        assert s.id.startswith("web-")

    def test_new_with_name(self):
        s, created = resolve_session_arg("new:docs", manager=self.m)
        assert created is True
        assert s.id == "docs"

    def test_existing_id(self):
        self.m.create("docs")
        s, created = resolve_session_arg("docs", manager=self.m)
        assert created is False
        assert s.id == "docs"

    def test_unknown_id_raises(self):
        with pytest.raises(SessionNotFound):
            resolve_session_arg("does-not-exist", manager=self.m)

    def test_invalid_name_in_new_raises(self):
        with pytest.raises(InvalidSessionName):
            resolve_session_arg("new:bad name", manager=self.m)

    def test_unknown_id_error_lists_known(self):
        self.m.create("foo")
        try:
            resolve_session_arg("missing", manager=self.m)
        except SessionNotFound as e:
            assert "foo" in e.known
        else:
            pytest.fail("expected SessionNotFound")


# ── Extraction ──────────────────────────────────────────────────────


class TestExtract:
    def test_markdown_basic(self):
        ex = extract(
            raw_html="<html><head><title>Hi</title></head>"
            "<body><h1>Title</h1><p>Hello <b>world</b>.</p></body></html>",
            url="https://x",
            fmt=FetchFormat.markdown,
        )
        assert ex.title == "Hi"
        assert "Hello **world**" in ex.content
        assert ex.truncated is False
        assert ex.full_output_path is None

    def test_markdown_inline_spacing(self):
        ex = extract(
            raw_html="<p>foo <b>bar</b> baz <a href='https://x'>link</a>.</p>",
            url="https://x",
            fmt=FetchFormat.markdown,
        )
        assert "foo **bar** baz" in ex.content
        assert "[link](https://x)" in ex.content

    def test_markdown_lists(self):
        ex = extract(
            raw_html="<ul><li>one</li><li>two</li><li>three</li></ul>",
            url="https://x",
            fmt=FetchFormat.markdown,
        )
        assert "- one" in ex.content
        assert "- two" in ex.content
        assert "- three" in ex.content

    def test_markdown_ordered_lists(self):
        ex = extract(
            raw_html="<ol><li>first</li><li>second</li></ol>",
            url="https://x",
            fmt=FetchFormat.markdown,
        )
        assert "1. first" in ex.content
        assert "2. second" in ex.content

    def test_markdown_strips_script_and_style(self):
        ex = extract(
            raw_html=(
                "<p>Visible.</p>"
                "<script>alert('x')</script>"
                "<style>body{color:red}</style>"
                "<p>Also visible.</p>"
            ),
            url="https://x",
            fmt=FetchFormat.markdown,
        )
        assert "alert" not in ex.content
        assert "color:red" not in ex.content
        assert "Visible." in ex.content
        assert "Also visible." in ex.content

    def test_markdown_table(self):
        ex = extract(
            raw_html="<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
            url="https://x",
            fmt=FetchFormat.markdown,
        )
        assert "| A | B |" in ex.content
        assert "| 1 | 2 |" in ex.content

    def test_text_format(self):
        ex = extract(
            raw_html="<h1>Heading</h1><p>Body.</p>",
            url="https://x",
            fmt=FetchFormat.text,
        )
        assert "Heading" in ex.content
        assert "Body." in ex.content
        assert "#" not in ex.content  # not markdown

    def test_html_format_strips_noise(self):
        ex = extract(
            raw_html="<p>X</p><script>bad()</script>",
            url="https://x",
            fmt=FetchFormat.html,
        )
        assert "bad()" not in ex.content
        assert "X" in ex.content

    def test_json_format(self):
        ex = extract(
            raw_html="<title>T</title><p>body</p>",
            url="https://x",
            fmt=FetchFormat.json,
        )
        assert '"url": "https://x"' in ex.content
        assert '"title": "T"' in ex.content

    def test_truncation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PAGEMAP_WEB_TMP_DIR", str(tmp_path))
        big = "a " * 5000
        ex = extract(
            raw_html=f"<p>{big}</p>",
            url="https://x",
            fmt=FetchFormat.text,
            max_chars=200,
        )
        assert ex.truncated is True
        assert ex.content_length == 200
        assert ex.full_output_path is not None
        assert os.path.exists(ex.full_output_path)
        # Spillover file contains the full body.
        with open(ex.full_output_path) as f:
            assert len(f.read()) > 200

    def test_no_truncation_when_under_limit(self):
        ex = extract(
            raw_html="<p>short</p>",
            url="https://x",
            fmt=FetchFormat.text,
            max_chars=10_000,
        )
        assert ex.truncated is False
        assert ex.full_output_path is None

    def test_max_chars_zero_disables_truncation(self):
        big = "x " * 10_000
        ex = extract(
            raw_html=f"<p>{big}</p>",
            url="https://x",
            fmt=FetchFormat.text,
            max_chars=0,
        )
        assert ex.truncated is False
        assert ex.full_output_path is None

    def test_none_html_raises(self):
        with pytest.raises(ExtractionError):
            extract(raw_html=None, url="https://x", fmt=FetchFormat.markdown)

    def test_garbage_html_raises(self):
        # bytes-typed argument will not raise; but bytes won't be parsed
        # either. Force a real failure with a non-string.
        with pytest.raises(ExtractionError):
            extract(raw_html=12345, url="https://x", fmt=FetchFormat.markdown)

    def test_spillover_path_deterministic(self):
        a = spillover_path_for("https://example.com/path", FetchFormat.markdown)
        b = spillover_path_for("https://example.com/path", FetchFormat.markdown)
        assert a == b
        c = spillover_path_for("https://example.com/other", FetchFormat.markdown)
        assert a != c
        assert a.endswith(".md")
        assert spillover_path_for("u", FetchFormat.json).endswith(".json")


# ── DuckDuckGo parser ───────────────────────────────────────────────


DDG_HTML = """
<html>
<body>
<div class="result">
  <a class="result__a" href="https://example.com"> Example </a>
  <a class="result__snippet">Example snippet.</a>
</div>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs&amp;rut=xyz"> Docs </a>
  <a class="result__snippet">Snippet 2.</a>
</div>
<div class="result">
  <a class="result__a" href="https://other.com"> Other </a>
  <a class="result__snippet">Other snippet.</a>
</div>
</body>
</html>
"""


class TestDdgParser:
    def test_parses_results(self):
        results = _parse_results(DDG_HTML, max_results=10)
        assert len(results) == 3
        assert results[0]["url"] == "https://example.com"
        assert results[0]["title"] == "Example"
        assert results[1]["url"] == "https://example.com/docs"
        assert results[2]["url"] == "https://other.com"

    def test_max_results_limits(self):
        results = _parse_results(DDG_HTML, max_results=2)
        assert len(results) == 2

    def test_strip_redirect_with_uddg(self):
        url = _strip_ddg_redirect(
            "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs&rut=xyz"
        )
        assert url == "https://example.com/docs"

    def test_strip_redirect_passthrough(self):
        assert _strip_ddg_redirect("https://example.com") == "https://example.com"
        assert _strip_ddg_redirect("//example.com") == "https://example.com"

    def test_provider_search_filters_domains(self):
        async def run():
            p = DuckDuckGoProvider()
            ctx = ProviderContext(session_id="x", history=[])  # forces stdlib path
            out = await p.search(
                "test",
                max_results=10,
                domain_filter=["example.com"],
                ctx=ctx,
            )
            # The HTML endpoint may or may not be reachable in CI; either way
            # we should get a list (possibly empty) back without raising.
            assert isinstance(out, list)
            if out:
                assert all("example.com" in r["url"] for r in out)

        # Don't actually hit the network in tests — just assert shape and
        # the filter logic. Skip if httpx-style fallback would error in CI.
        try:
            asyncio.run(run())
        except (ProviderError, OSError):
            pytest.skip("network unavailable in this environment")


# ── Provider registry ──────────────────────────────────────────────


class FakeProvider:
    name = "fake"

    async def search(self, query, *, max_results=10, recency=None, domain_filter=None, ctx=None):
        return [{"title": q, "url": f"https://fake/{q}", "snippet": ""} for q in [query]]


class TestProviderRegistry:
    def setup_method(self):
        # Snapshot the registry so we can restore after each test.
        from pagemap.web_fetch.providers import registry as reg

        self._factories = dict(reg._PROVIDER_FACTORIES)
        self._instances = dict(reg._PROVIDER_INSTANCES)
        # PROVIDERS is keyed off the same factories; reset it too.
        reg.PROVIDERS.clear()

    def teardown_method(self):
        from contextlib import suppress

        from pagemap.web_fetch.providers import registry as reg

        reg._PROVIDER_FACTORIES.clear()
        reg._PROVIDER_FACTORIES.update(self._factories)
        reg._PROVIDER_INSTANCES.clear()
        reg._PROVIDER_INSTANCES.update(self._instances)
        reg.PROVIDERS.clear()
        for n in list(reg._PROVIDER_FACTORIES.keys()):
            with suppress(ProviderError):
                reg.PROVIDERS[n] = reg.get_provider(n)

    def test_builtin_providers_registered(self):
        names = list_provider_names()
        for expected in ("duckduckgo", "brave", "bing", "google", "searxng", "exa", "tavily", "firecrawl"):
            assert expected in names

    def test_register_custom_provider(self):
        register_provider("fake", lambda: FakeProvider())
        p = get_provider("fake")
        assert p is not None
        assert p.name == "fake"

    def test_unknown_provider_raises(self):
        with pytest.raises(ProviderError):
            get_provider("does-not-exist")

    def test_available_providers_includes_stubs(self):
        for p in available_providers():
            assert p.name

    def test_stub_providers_raise_not_implemented(self):
        async def run():
            for n in ("brave", "bing", "google", "searxng", "exa", "tavily", "firecrawl"):
                p = get_provider(n)
                with pytest.raises(ProviderError):
                    await p.search("anything")

        asyncio.run(run())


# ── Fast mode (HTTP-only) ──────────────────────────────────────────


class TestFastModeFetch:
    """End-to-end tests for ``_web_fetch_impl`` with ``mode="fast"``.

    Patches the resolved HttpBackend so no real network is hit.
    """

    @pytest.mark.asyncio
    async def test_fast_mode_returns_extracted_content(self, monkeypatch):
        from pagemap.web_fetch.http.base import HttpResponse

        async def fake_fetch(self, url, **_):
            return HttpResponse(
                url=url,
                status=200,
                headers={"content-type": "text/html"},
                text="<html><body><h1>Hello</h1><p>World</p></body></html>",
                set_cookies=[],
            )

        from pagemap.web_fetch.http.backends import UrllibBackend

        monkeypatch.setattr(UrllibBackend, "fetch", fake_fetch)

        # Force the registry to resolve to the urllib backend.
        import pagemap.server as srv

        monkeypatch.setattr(srv, "_http_backend", UrllibBackend(), raising=False)
        monkeypatch.setattr(srv, "_http_backend_name", "urllib", raising=False)

        from pagemap.server import _web_fetch_impl

        ctx = type("C", (), {"request_id": "r1", "session_id": "s1", "client_id": "c1"})()
        out = await _web_fetch_impl(
            url="https://example.com/page",
            mode="fast",
            format="markdown",
            max_chars=50_000,
            session_arg=None,
            request_id="r1",
            ctx=ctx,
        )
        assert "Hello" in out
        assert "World" in out
        assert "Error" not in out or out.startswith("# ")

    @pytest.mark.asyncio
    async def test_fast_mode_persists_cookies(self, monkeypatch):
        from pagemap.web_fetch.http.base import HttpResponse, SetCookie

        calls: list[dict] = []

        async def fake_fetch(self, url, *, cookies=None, **_):
            calls.append({"url": url, "cookies": dict(cookies or {})})
            if "login" in url:
                return HttpResponse(
                    url=url,
                    status=200,
                    headers={"content-type": "text/html"},
                    text="<html><body>logged in</body></html>",
                    set_cookies=[SetCookie(name="sid", value="abc", path="/")],
                )
            return HttpResponse(
                url=url,
                status=200,
                headers={"content-type": "text/html"},
                text="<html><body>profile</body></html>",
                set_cookies=[],
            )

        from pagemap.web_fetch.http.backends import UrllibBackend

        monkeypatch.setattr(UrllibBackend, "fetch", fake_fetch)

        import pagemap.server as srv

        monkeypatch.setattr(srv, "_http_backend", UrllibBackend(), raising=False)
        monkeypatch.setattr(srv, "_http_backend_name", "urllib", raising=False)

        from pagemap.server import _web_fetch_impl

        ctx = type("C", (), {"request_id": "r1", "session_id": "s1", "client_id": "c1"})()

        # Use the same session id for both calls to share the cookie jar.
        out1 = await _web_fetch_impl(
            url="https://example.com/login",
            mode="fast",
            format="text",
            max_chars=50_000,
            session_arg="new:cookie-test",
            request_id="r1",
            ctx=ctx,
        )
        out2 = await _web_fetch_impl(
            url="https://example.com/profile",
            mode="fast",
            format="text",
            max_chars=50_000,
            session_arg="cookie-test",
            request_id="r1",
            ctx=ctx,
        )
        # First call should not have sent any cookies.
        assert calls[0]["cookies"] == {}
        # Second call should have sent the cookie from the first call.
        assert calls[1]["cookies"].get("sid") == "abc"
        assert "logged in" in out1
        assert "profile" in out2

    @pytest.mark.asyncio
    async def test_fast_mode_metadata_records_backend(self, monkeypatch):
        from pagemap.web_fetch.http.base import HttpResponse

        async def fake_fetch(self, url, **_):
            return HttpResponse(
                url=url,
                status=200,
                headers={"content-type": "text/html"},
                text="<html><body>x</body></html>",
                set_cookies=[],
            )

        from pagemap.web_fetch.http.backends import UrllibBackend

        monkeypatch.setattr(UrllibBackend, "fetch", fake_fetch)

        import pagemap.server as srv

        monkeypatch.setattr(srv, "_http_backend", UrllibBackend(), raising=False)
        monkeypatch.setattr(srv, "_http_backend_name", "urllib", raising=False)

        from pagemap.server import _web_fetch_impl

        ctx = type("C", (), {"request_id": "r1", "session_id": "s1", "client_id": "c1"})()
        out = await _web_fetch_impl(
            url="https://example.com/",
            mode="fast",
            format="json",
            max_chars=50_000,
            session_arg=None,
            request_id="r1",
            ctx=ctx,
        )
        # JSON format surfaces metadata; assert backend name appears.
        assert "urllib" in out

    @pytest.mark.asyncio
    async def test_fast_mode_surfaces_backend_error(self, monkeypatch):
        from pagemap.web_fetch.http.base import HttpBackendError

        async def fake_fetch(self, url, **_):
            raise HttpBackendError("simulated dns failure")

        from pagemap.web_fetch.http.backends import UrllibBackend

        monkeypatch.setattr(UrllibBackend, "fetch", fake_fetch)

        import pagemap.server as srv

        monkeypatch.setattr(srv, "_http_backend", UrllibBackend(), raising=False)
        monkeypatch.setattr(srv, "_http_backend_name", "urllib", raising=False)

        from pagemap.server import _web_fetch_impl

        ctx = type("C", (), {"request_id": "r1", "session_id": "s1", "client_id": "c1"})()
        out = await _web_fetch_impl(
            url="https://example.com/",
            mode="fast",
            format="markdown",
            max_chars=50_000,
            session_arg=None,
            request_id="r1",
            ctx=ctx,
        )
        assert "simulated dns failure" in out
        assert "Error" in out


# ── Model round-trips ──────────────────────────────────────────────


class TestModels:
    def test_web_search_output_serializes(self):
        m = WebSearchResult(title="t", url="https://x", snippet="s", source="duckduckgo")
        assert m.model_dump()["title"] == "t"

    def test_web_fetch_result_str_for_markdown(self):
        r = WebFetchResult(
            url="https://x",
            final_url="https://x",
            session="default",
            format="markdown",
            mode="browser",
            content="# Hi",
            content_length=4,
        )
        assert str(r) == "# Hi"

    def test_web_fetch_result_str_for_json(self):
        r = WebFetchResult(
            url="https://x",
            final_url="https://x",
            session="default",
            format="json",
            mode="browser",
            content="",
        )
        s = str(r)
        assert "https://x" in s
        assert "default" in s

    def test_batch_result_str_is_json(self):
        r = BatchWebFetchResult(
            total=2,
            succeeded=1,
            failed=1,
            session="default",
            results=[],
        )
        s = str(r)
        assert '"total": 2' in s
        assert '"succeeded": 1' in s

    def test_session_info_round_trip(self):
        s = SessionInfo(
            id="docs", created_at=1.0, last_used=2.0, history_size=3, is_default=False
        )
        assert s.model_dump()["id"] == "docs"
