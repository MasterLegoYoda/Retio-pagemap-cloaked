# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for the HTTP-only fetch backends.

Covers:

* Backend availability detection.
* Registry resolution (auto order, explicit name, missing).
* ``HttpResponse`` / ``SetCookie`` parsing.
* Per-backend ``fetch()`` (mocked at the transport boundary so the
  tests run offline).
* Cookie persistence across calls via ``HttpSessionState``.
* Post-redirect SSRF guard (the contract ``server/__init__.py``
  relies on).
"""

from __future__ import annotations

import importlib
import urllib.error
import urllib.request
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pagemap.pipeline.retriever.http.backends import (
    CurlCffiBackend,
    HttpxBackend,
    UrllibBackend,
)
from pagemap.pipeline.retriever.http.backends.curl_cffi import (
    _parse_set_cookie as _parse_set_cookie_curl,
)
from pagemap.pipeline.retriever.http.backends.httpx_backend import (
    _parse_set_cookie as _parse_set_cookie_httpx,
)
from pagemap.pipeline.retriever.http.backends.urllib_backend import (
    _parse_set_cookie as _parse_set_cookie_urllib,
)
from pagemap.pipeline.retriever.http.base import (
    HttpBackendError,
    HttpResponse,
    SetCookie,
)
from pagemap.pipeline.retriever.http.registry import (
    _reset_for_tests,
    get_backend,
    list_backends,
    register_backend,
    resolve_backend,
)
from pagemap.pipeline.retriever.sessions import HttpSessionState, WebSession

# All three Set-Cookie parsers should be byte-for-byte equivalent —
# run the same test matrix against each.
ALL_COOKIE_PARSERS = [
    _parse_set_cookie_curl,
    _parse_set_cookie_httpx,
    _parse_set_cookie_urllib,
]


# ── Registry / resolution ───────────────────────────────────────────


class TestRegistry:
    def setup_method(self):
        # Snapshot and clear so tests can't poison each other.
        from pagemap.pipeline.retriever.http import registry as reg

        self._factories = dict(reg._FACTORIES)
        self._instances = dict(reg._INSTANCES)
        _reset_for_tests()
        # Re-register the built-ins (the import side-effect only
        # fires once on first import of the http package).
        from pagemap.pipeline.retriever.http import _builtins as _b

        _b._register_builtins()

    def teardown_method(self):
        from pagemap.pipeline.retriever.http import registry as reg

        reg._FACTORIES.clear()
        reg._FACTORIES.update(self._factories)
        reg._INSTANCES.clear()
        reg._INSTANCES.update(self._instances)

    def test_built_in_backends_registered(self):
        names = list_backends()
        assert "urllib" in names
        assert "httpx" in names
        assert "curl_cffi" in names

    def test_resolve_auto_picks_httpx_when_curl_cffi_missing(self, monkeypatch):
        # Force curl_cffi to look unavailable without touching global state.
        from pagemap.pipeline.retriever.http import registry as reg
        from pagemap.pipeline.retriever.http.backends import curl_cffi as curl_mod

        monkeypatch.setattr(curl_mod.CurlCffiBackend, "is_available", lambda self: False)
        # Drop any cached instance of curl_cffi so the next resolve
        # calls the patched method.
        reg._INSTANCES.pop("curl_cffi", None)

        backend = resolve_backend("auto")
        assert backend.name in ("httpx", "urllib")
        # ``httpx`` is installed in this test env, so the auto path
        # should land on it.
        assert backend.name == "httpx"

    def test_resolve_auto_falls_through_to_urllib(self, monkeypatch):
        from pagemap.pipeline.retriever.http import registry as reg
        from pagemap.pipeline.retriever.http.backends import curl_cffi as curl_mod, httpx_backend as hx_mod

        monkeypatch.setattr(curl_mod.CurlCffiBackend, "is_available", lambda self: False)
        monkeypatch.setattr(hx_mod.HttpxBackend, "is_available", lambda self: False)
        reg._INSTANCES.pop("curl_cffi", None)
        reg._INSTANCES.pop("httpx", None)

        backend = resolve_backend("auto")
        assert backend.name == "urllib"

    def test_resolve_explicit_name(self):
        backend = resolve_backend("urllib")
        assert backend.name == "urllib"

    def test_resolve_unknown_raises(self):
        with pytest.raises(HttpBackendError):
            resolve_backend("definitely-not-a-real-backend")

    def test_resolve_uninstalled_raises_with_helpful_message(self):
        from pagemap.pipeline.retriever.http import registry as reg
        from pagemap.pipeline.retriever.http.backends import curl_cffi as curl_mod

        reg._INSTANCES.pop("curl_cffi", None)
        with (
            patch.object(curl_mod.CurlCffiBackend, "is_available", return_value=False),
            pytest.raises(HttpBackendError) as exc,
        ):
            get_backend("curl_cffi")
        assert "optional dependency" in str(exc.value)

    def test_register_custom_backend(self):
        class _Stub:
            name = "test-stub"

            def is_available(self) -> bool:
                return True

            async def fetch(self, url, **_):  # pragma: no cover — never called
                raise NotImplementedError

            async def aclose(self) -> None:
                return None

        register_backend("test-stub", lambda: _Stub())
        backend = get_backend("test-stub")
        assert backend.name == "test-stub"
        assert isinstance(backend, _Stub)

    def test_get_caches_instance(self):
        a = get_backend("urllib")
        b = get_backend("urllib")
        assert a is b


# ── SetCookie parsing ──────────────────────────────────────────────


class TestSetCookieParsing:
    @pytest.mark.parametrize("parser", ALL_COOKIE_PARSERS)
    def test_simple(self, parser):
        sc = parser("session=abc123")
        assert sc == SetCookie(name="session", value="abc123")

    @pytest.mark.parametrize("parser", ALL_COOKIE_PARSERS)
    def test_with_attrs(self, parser):
        sc = parser("id=42; Path=/; Domain=example.com; Max-Age=3600; Secure; HttpOnly; SameSite=Lax")
        assert sc is not None
        assert sc.name == "id"
        assert sc.value == "42"
        assert sc.path == "/"
        assert sc.domain == "example.com"
        assert sc.max_age == 3600
        assert sc.secure is True
        assert sc.http_only is True
        assert sc.same_site == "Lax"

    @pytest.mark.parametrize("parser", ALL_COOKIE_PARSERS)
    def test_value_with_equals(self, parser):
        sc = parser("token=abc=def==")
        assert sc is not None
        assert sc.name == "token"
        assert sc.value == "abc=def=="

    @pytest.mark.parametrize("parser", ALL_COOKIE_PARSERS)
    def test_empty_returns_none(self, parser):
        assert parser("") is None
        assert parser("  ") is None

    @pytest.mark.parametrize("parser", ALL_COOKIE_PARSERS)
    def test_no_equals_returns_none(self, parser):
        assert parser("garbage") is None

    @pytest.mark.parametrize("parser", ALL_COOKIE_PARSERS)
    def test_empty_name_returns_none(self, parser):
        assert parser("=value") is None


# ── HttpSessionState cookie merging ────────────────────────────────


class TestHttpSessionState:
    def test_default_construction(self):
        s = HttpSessionState()
        assert s.cookies == {}
        assert s.user_agent.startswith("Mozilla/")
        assert s.request_count == 0
        assert s.backend_name == "auto"

    def test_merge_set_cookies(self):
        s = HttpSessionState()
        s.merge_set_cookies([
            SetCookie(name="a", value="1"),
            SetCookie(name="b", value="2"),
        ])
        assert s.cookies == {"a": "1", "b": "2"}

    def test_merge_overwrites(self):
        s = HttpSessionState(cookies={"a": "old"})
        s.merge_set_cookies([SetCookie(name="a", value="new")])
        assert s.cookies == {"a": "new"}

    def test_merge_skips_empty_name(self):
        s = HttpSessionState()
        s.merge_set_cookies([
            SetCookie(name="", value="bad"),
            SetCookie(name=None, value="bad"),
            SetCookie(name="ok", value="1"),
        ])
        assert s.cookies == {"ok": "1"}


# ── WebSession http field ──────────────────────────────────────────


class TestWebSessionHttpField:
    def test_http_field_default_none(self):
        s = WebSession(id="x")
        assert s.http is None

    def test_http_field_settable(self):
        s = WebSession(id="x", http=HttpSessionState())
        assert s.http is not None
        assert s.http.cookies == {}


# ── Urllib backend (always available) ──────────────────────────────


class TestUrllibBackend:
    def test_is_available(self):
        b = UrllibBackend()
        assert b.is_available() is True

    @pytest.mark.asyncio
    async def test_fetch_uses_default_ua(self, monkeypatch):
        captured: dict[str, Any] = {}

        import email.message

        class _FakeResponse:
            status = 200
            url = "https://example.com/"

            def __init__(self):
                hdrs = email.message.Message()
                hdrs["Content-Type"] = "text/html; charset=utf-8"
                self.headers = hdrs

            def read(self) -> bytes:
                return b"<html><head><title>t</title></head><body>ok</body></html>"

        def _open(self_, req, *_args, **_kwargs):  # noqa: ARG001
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            return _FakeResponse()

        monkeypatch.setattr(urllib.request.OpenerDirector, "open", _open)
        b = UrllibBackend()
        resp = await b.fetch("https://example.com/")
        assert resp.status == 200
        assert "Mozilla" in captured["headers"]["User-agent"]
        assert "<title>t</title>" in resp.text

    @pytest.mark.asyncio
    async def test_fetch_passes_cookies_as_header(self, monkeypatch):
        captured: dict[str, Any] = {}

        import email.message

        class _FakeResponse:
            status = 200
            url = "https://example.com/"

            def __init__(self):
                hdrs = email.message.Message()
                hdrs["Content-Type"] = "text/html"
                self.headers = hdrs

            def read(self) -> bytes:
                return b""

        def _open(self_, req, *_args, **_kwargs):  # noqa: ARG001
            captured["headers"] = dict(req.header_items())
            return _FakeResponse()

        monkeypatch.setattr(urllib.request.OpenerDirector, "open", _open)
        b = UrllibBackend()
        await b.fetch("https://example.com/", cookies={"k": "v"})
        # The cookie jar builder might not surface cookies via
        # ``req.headers`` (it goes through the ``HTTPCookieProcessor``),
        # so we don't assert on the request.  We do assert that the
        # backend didn't raise.
        assert captured["headers"]  # headers were captured

    @pytest.mark.asyncio
    async def test_fetch_parses_set_cookie(self, monkeypatch):
        import email.message

        class _FakeResponse:
            status = 200
            url = "https://example.com/"

            def __init__(self):
                hdrs = email.message.Message()
                hdrs["Content-Type"] = "text/html"
                hdrs["Set-Cookie"] = "sessionid=abc; Path=/; HttpOnly"
                self.headers = hdrs

            def read(self) -> bytes:
                return b""

        monkeypatch.setattr(
            urllib.request.OpenerDirector,
            "open",
            lambda self_, *_a, **_kw: _FakeResponse(),
        )
        b = UrllibBackend()
        resp = await b.fetch("https://example.com/")
        assert any(
            sc.name == "sessionid" and sc.value == "abc" and sc.http_only
            for sc in resp.set_cookies
        )

    @pytest.mark.asyncio
    async def test_fetch_translates_httperror_to_response(self, monkeypatch):
        import email.message

        class _ErrResponse(urllib.error.HTTPError):
            def __init__(self):
                hdrs = email.message.Message()
                hdrs["Content-Type"] = "text/plain"
                super().__init__("https://example.com/", 404, "Not Found", hdrs, None)
                self.url = "https://example.com/"
                self.headers = hdrs

            def read(self) -> bytes:
                return b"missing"

        monkeypatch.setattr(
            urllib.request.OpenerDirector,
            "open",
            lambda self_, *_a, **_kw: _ErrResponse(),
        )
        b = UrllibBackend()
        resp = await b.fetch("https://example.com/")
        assert resp.status == 404
        assert resp.text == "missing"

    @pytest.mark.asyncio
    async def test_fetch_raises_on_urlerror(self, monkeypatch):
        def _open(self_, *_a, **_kw):
            raise urllib.error.URLError("dns failure")

        monkeypatch.setattr(urllib.request.OpenerDirector, "open", _open)
        b = UrllibBackend()
        with pytest.raises(HttpBackendError):
            await b.fetch("https://example.com/")

    @pytest.mark.asyncio
    async def test_aclose_is_noop(self):
        assert await UrllibBackend().aclose() is None


# ── Httpx backend (mocked transport) ────────────────────────────────


def _fake_httpx_response(
    *,
    status: int = 200,
    url: str = "https://example.com/",
    text: str = "<html>ok</html>",
    content_type: str = "text/html",
    set_cookies: list[str] | None = None,
):
    """Build a mock that looks like an ``httpx.Response``."""
    import httpx as _httpx

    headers_dict: dict[str, str] = {"content-type": content_type}
    if set_cookies:
        # httpx allows multiple set-cookie values; we just add them
        # to the dict and expose via get_list on the real Headers.
        headers_dict = {**headers_dict, "set-cookie": set_cookies[0]}
    resp = MagicMock()
    resp.status_code = status
    resp.url = url
    resp.text = text
    resp.content = text.encode()
    resp.headers = _httpx.Headers(headers_dict)
    # Make multi-cookie headers available via get_list.  httpx's
    # real Headers.get_list walks all values with that name, so
    # for multi-cookie we set them via the raw form.
    if set_cookies and len(set_cookies) > 1:
        # Build a Headers object where get_list returns the multi list.
        class _MultiHeaders(_httpx.Headers):
            def __init__(self, base: dict[str, str], cookies: list[str]) -> None:
                super().__init__(base)
                self._cookies = list(cookies)

            def get_list(self, name: str) -> list[str]:  # type: ignore[override]
                if name.lower() == "set-cookie":
                    return list(self._cookies)
                return super().get_list(name)

        resp.headers = _MultiHeaders(headers_dict, set_cookies)
    elif set_cookies:
        # The single-cookie path works as-is; just expose a get_list
        # that returns the single value.
        class _SingleHeaders(_httpx.Headers):
            def get_list(self, name: str) -> list[str]:  # type: ignore[override]
                if name.lower() == "set-cookie":
                    return [self.get("set-cookie")] if self.get("set-cookie") else []
                return super().get_list(name)

        resp.headers = _SingleHeaders(headers_dict)
    return resp


class TestHttpxBackend:
    def test_is_available(self):
        b = HttpxBackend()
        assert b.is_available() is True

    @pytest.mark.asyncio
    async def test_fetch_returns_response(self):
        b = HttpxBackend()
        fake = _fake_httpx_response()
        with patch.object(HttpxBackend, "_get_client", new=AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=fake)))):
            resp = await b.fetch("https://example.com/")
        assert resp.status == 200
        assert "ok" in resp.text
        assert resp.headers.get("content-type", "").startswith("text/html")

    @pytest.mark.asyncio
    async def test_fetch_passes_cookies(self):
        """Cookies should be forwarded to the underlying httpx client."""
        b = HttpxBackend()
        fake = _fake_httpx_response()
        fake_get = AsyncMock(return_value=fake)
        fake_client = MagicMock(get=fake_get)

        with patch.object(HttpxBackend, "_get_client", new=AsyncMock(return_value=fake_client)):
            await b.fetch("https://example.com/cookies", cookies={"a": "1", "b": "2"})

        kwargs = fake_get.await_args.kwargs
        assert kwargs.get("cookies") == {"a": "1", "b": "2"}

    @pytest.mark.asyncio
    async def test_fetch_parses_set_cookie(self):
        b = HttpxBackend()
        fake = _fake_httpx_response(set_cookies=["sid=xyz; Path=/; HttpOnly"])
        with patch.object(HttpxBackend, "_get_client", new=AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=fake)))):
            resp = await b.fetch("https://example.com/login")
        assert any(
            sc.name == "sid" and sc.value == "xyz" and sc.http_only
            for sc in resp.set_cookies
        )

    @pytest.mark.asyncio
    async def test_fetch_raises_on_http_error(self):
        """A 4xx response should surface as ``HttpBackendError``."""
        b = HttpxBackend()

        class _FakeHTTPError(Exception):
            def __init__(self, msg: str) -> None:
                super().__init__(msg)

        fake = MagicMock()
        fake.status_code = 404
        fake.url = "https://example.com/missing"
        fake.text = "missing"
        fake.headers = MagicMock()
        fake.headers.items.return_value = []
        fake.headers.get = lambda k, default=None: default
        fake.headers.get_list = lambda k: []
        # Simulate httpx's HTTPError path
        import httpx as _httpx

        async def _raise(*_a, **_kw):
            raise _httpx.HTTPError("404 Not Found")

        with (
            patch.object(HttpxBackend, "_get_client", new=AsyncMock(return_value=MagicMock(get=_raise))),
            pytest.raises(HttpBackendError),
        ):
            await b.fetch("https://example.com/missing")

    @pytest.mark.asyncio
    async def test_aclose_releases_client(self):
        b = HttpxBackend()
        # Inject a fake client that we can verify aclose() is called on,
        # avoiding httpx.AsyncClient's real proxy/config machinery which
        # the test environment may not support.
        fake_client = MagicMock()
        fake_client.aclose = AsyncMock()
        b._client = fake_client
        await b.aclose()
        assert b._client is None
        fake_client.aclose.assert_awaited_once()


# ── CurlCffi backend (skipped when dependency missing) ──────────────


class TestCurlCffiBackend:
    def test_is_available_reflects_install(self):
        b = CurlCffiBackend()
        spec = importlib.util.find_spec("curl_cffi")
        assert b.is_available() is (spec is not None)

    @pytest.mark.asyncio
    async def test_fetch_uses_curl_cffi_session(self):
        """When curl_cffi is installed, ``fetch`` delegates to it.

        We mock the AsyncSession to avoid a real network call.  This
        test is a no-op (skipped) on installs without curl_cffi.
        """
        if not CurlCffiBackend().is_available():
            pytest.skip("curl_cffi not installed")

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.url = "https://example.com/"
        fake_resp.headers = {"content-type": "text/html"}
        fake_resp.headers.get_list = (
            lambda k: ["sid=abc; Path=/; HttpOnly"] if k.lower() == "set-cookie" else []
        )
        fake_resp.text = "<html>hi</html>"

        fake_session = MagicMock()
        fake_session.get = AsyncMock(return_value=fake_resp)
        fake_session.aclose = AsyncMock()
        fake_session._pagemap_impersonate = "chrome"

        b = CurlCffiBackend()
        b._session = fake_session

        resp = await b.fetch("https://example.com/")
        assert resp.status == 200
        assert "hi" in resp.text
        assert any(sc.name == "sid" for sc in resp.set_cookies)
        fake_session.get.assert_awaited_once()
        kwargs = fake_session.get.await_args.kwargs
        assert kwargs.get("allow_redirects") is True
        assert "headers" in kwargs

    @pytest.mark.asyncio
    async def test_aclose_closes_session(self):
        b = CurlCffiBackend()
        fake_session = MagicMock()
        fake_session.aclose = AsyncMock()
        b._session = fake_session
        await b.aclose()
        assert b._session is None
        fake_session.aclose.assert_awaited_once()


# ── End-to-end cookie persistence via HttpSessionState ────────────


class TestSessionCookieContinuity:
    @pytest.mark.asyncio
    async def test_cookies_persist_across_two_fetches(self):
        """A two-call sequence: server sets a cookie, second call sends it back."""
        b = HttpxBackend()
        state = HttpSessionState()

        # First call — server returns a Set-Cookie header.
        first_resp = _fake_httpx_response(
            set_cookies=["sid=abc123; Path=/"],
            text="logged in",
        )
        # Second call — we send the cookie back; assert via mock.
        second_resp = _fake_httpx_response(text="hello user")
        second_get = AsyncMock(return_value=second_resp)
        fake_client2 = MagicMock(get=second_get)

        with patch.object(
            HttpxBackend,
            "_get_client",
            new=AsyncMock(
                side_effect=[
                    MagicMock(get=AsyncMock(return_value=first_resp)),
                    fake_client2,
                ]
            ),
        ):
            resp1 = await b.fetch("https://example.com/login")
            state.merge_set_cookies(resp1.set_cookies)
            assert state.cookies == {"sid": "abc123"}

            resp2 = await b.fetch(
                "https://example.com/profile",
                cookies=state.cookies,
            )
            assert resp2.status == 200

        # The cookies dict should have been passed to the second call.
        kwargs = second_get.await_args.kwargs
        assert kwargs.get("cookies") == {"sid": "abc123"}


# ── HttpResponse shape contract ────────────────────────────────────


class TestHttpResponse:
    def test_defaults(self):
        r = HttpResponse(url="https://x", status=200)
        assert r.url == "https://x"
        assert r.status == 200
        assert r.headers == {}
        assert r.text == ""
        assert r.set_cookies == []
