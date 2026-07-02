"""Named-session management for the web fetch / search layer.

A ``WebSession`` is a logical container that owns a browser context (lazily
created) and records an activity history so successive searches and fetches
look continuous to bot detection. Sessions are resolved through
``SessionManager`` with stable ids.

Resolution rules for the ``session`` argument on tools:

* ``None`` -> use the long-lived ``"default"`` session (created lazily).
* ``"new"`` -> create a fresh session with a generated id (``web-<uuid12>``).
* ``"new:<name>"`` -> create a fresh session with the validated explicit name.
* any other string -> load that session by id; raise ``SessionNotFound`` if unknown.
"""

from __future__ import annotations

import os
import re
import time as _time
import uuid
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from .errors import InvalidSessionName, SessionNotFound
from .models import SessionInfo

__all__ = [
    "DEFAULT_SESSION_ID",
    "NEW_SESSION_SENTINEL",
    "NEW_SESSION_PREFIX",
    "SESSION_NAME_PATTERN",
    "SessionManager",
    "WebSession",
    "resolve_session_arg",
]

DEFAULT_SESSION_ID = "default"
NEW_SESSION_SENTINEL = "new"
NEW_SESSION_PREFIX = "new:"
# Allow ``default``, generated ids (``web-<uuid>``), and explicit names.
SESSION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

_MAX_NAME_LEN = 64


def _validate_explicit_name(name: str) -> str:
    """Return ``name`` unchanged if valid, else raise ``InvalidSessionName``."""
    if not name:
        raise InvalidSessionName("Session name must not be empty.")
    if len(name) > _MAX_NAME_LEN:
        raise InvalidSessionName(
            f"Session name '{name[:16]}...' too long ({len(name)} chars, max {_MAX_NAME_LEN})."
        )
    if not SESSION_NAME_PATTERN.match(name):
        raise InvalidSessionName(
            f"Invalid session name '{name}'. Use [A-Za-z0-9][A-Za-z0-9_-]{{0,63}}."
        )
    if name == NEW_SESSION_SENTINEL:
        raise InvalidSessionName(f"Session name '{name}' is reserved.")
    return name


@dataclass
class WebSession:
    """A named web session.

    The ``browser`` attribute is intentionally ``Any`` to avoid hard-coupling
    to the PageMap ``BrowserSession`` type; the MCP layer wires it in.
    """

    id: str
    created_at: float = field(default_factory=_time.time)
    last_used: float = field(default_factory=_time.time)
    history: list[dict[str, Any]] = field(default_factory=list)
    browser: Any = None  # BrowserSession | None
    is_default: bool = False
    _closed: bool = field(default=False, init=False)

    def record(self, kind: str, **payload: Any) -> None:
        """Append a history entry and bump ``last_used``."""
        if self._closed:
            return
        entry = {"t": _time.time(), "kind": kind, **payload}
        self.history.append(entry)
        # Cap history to avoid unbounded growth.
        if len(self.history) > 512:
            self.history = self.history[-512:]
        self.last_used = _time.time()

    def touch(self) -> None:
        self.last_used = _time.time()

    def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def info(self) -> SessionInfo:
        return SessionInfo(
            id=self.id,
            created_at=self.created_at,
            last_used=self.last_used,
            history_size=len(self.history),
            is_default=self.is_default,
        )


def resolve_session_arg(
    arg: str | None,
    *,
    manager: SessionManager,
) -> tuple[WebSession, bool]:
    """Resolve a tool's ``session`` argument to a session + ``created`` flag.

    Returns:
        (session, created). ``created`` is True iff this call brought a
        previously unknown session into being (``"new"`` / ``"new:<name>"``).

    Raises:
        InvalidSessionName: explicit name fails validation.
        SessionNotFound: explicit id (not "new") is not in the registry.
    """
    if arg is None:
        return manager.get_or_create_default(), False
    if arg == NEW_SESSION_SENTINEL:
        return manager.create(), True
    if arg.startswith(NEW_SESSION_PREFIX):
        name = _validate_explicit_name(arg[len(NEW_SESSION_PREFIX) :])
        return manager.create(name), True
    # Look up by id (without validation, since generated ids always match the
    # pattern but legacy ids might exist).
    sess = manager.get(arg)
    if sess is None:
        raise SessionNotFound(arg, known=manager.ids())
    return sess, False


class SessionManager:
    """In-process registry of named web sessions.

    Thread-safe via a single re-entrant lock. Sessions are kept in memory
    only; restarting the server clears all sessions. Idle sessions past
    ``ttl_seconds`` are evicted on next access.
    """

    def __init__(self, *, ttl_seconds: float | None = None) -> None:
        self._sessions: dict[str, WebSession] = {}
        self._lock = RLock()
        if ttl_seconds is None:
            env = os.environ.get("PAGEMAP_WEB_SESSION_TTL_S", "").strip()
            try:
                ttl_seconds = float(env) if env else 1800.0
            except ValueError:
                ttl_seconds = 1800.0
        self._ttl_seconds = ttl_seconds

    # ── lookups ────────────────────────────────────────────────────

    def get(self, session_id: str) -> WebSession | None:
        with self._lock:
            self._evict_idle()
            return self._sessions.get(session_id)

    def get_or_create_default(self) -> WebSession:
        with self._lock:
            self._evict_idle()
            sess = self._sessions.get(DEFAULT_SESSION_ID)
            if sess is None:
                sess = WebSession(id=DEFAULT_SESSION_ID, is_default=True)
                self._sessions[DEFAULT_SESSION_ID] = sess
            return sess

    def ids(self) -> list[str]:
        with self._lock:
            self._evict_idle()
            return sorted(self._sessions.keys())

    def list_sessions(self) -> list[WebSession]:
        with self._lock:
            self._evict_idle()
            return list(self._sessions.values())

    # ── mutations ──────────────────────────────────────────────────

    def create(self, name: str | None = None) -> WebSession:
        if name is None:
            name = f"web-{uuid.uuid4().hex[:12]}"
        else:
            _validate_explicit_name(name)
        with self._lock:
            self._evict_idle()
            if name in self._sessions:
                # Idempotent create: return the existing session. This keeps
                # callers from having to retry when the name is taken.
                return self._sessions[name]
            sess = WebSession(id=name)
            self._sessions[name] = sess
            return sess

    def close(self, session_id: str) -> bool:
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.close()
            if not sess.is_default:
                del self._sessions[session_id]
            else:
                # Default: keep the slot but mark closed so the next call
                # recreates a fresh underlying browser context.
                self._sessions[session_id] = WebSession(
                    id=DEFAULT_SESSION_ID, is_default=True
                )
            return True

    def reset_default(self) -> WebSession:
        with self._lock:
            sess = WebSession(id=DEFAULT_SESSION_ID, is_default=True)
            self._sessions[DEFAULT_SESSION_ID] = sess
            return sess

    # ── helpers ────────────────────────────────────────────────────

    def _evict_idle(self) -> None:
        if self._ttl_seconds <= 0:
            return
        now = _time.time()
        expired: list[str] = []
        for sid, sess in self._sessions.items():
            if sess.is_default:
                continue  # never auto-evict the default
            if (now - sess.last_used) > self._ttl_seconds:
                expired.append(sid)
        for sid in expired:
            self._sessions.pop(sid, None)
