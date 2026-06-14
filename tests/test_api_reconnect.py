"""The web _Session reuses one Postgres connection but must transparently recover when Neon drops
it while idle (auto-suspend). These tests cover the reconnect-and-retry path without a real DB."""

import psycopg
import pytest

from api.app import _is_dead_connection, _Session


def _make_session() -> _Session:
    from uuid import uuid4

    return _Session(uuid4())


def test_detects_connection_level_errors():
    assert _is_dead_connection(psycopg.OperationalError("SSL connection has been closed unexpectedly"))
    assert _is_dead_connection(psycopg.InterfaceError("connection is closed"))
    assert not _is_dead_connection(ValueError("totally unrelated"))
    assert not _is_dead_connection(KeyError("requirements"))


async def test_reconnects_and_retries_once_on_dead_connection(monkeypatch):
    session = _make_session()

    reconnects = {"n": 0}

    async def fake_reconnect():
        reconnects["n"] += 1

    monkeypatch.setattr(session, "_reconnect", fake_reconnect)

    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        if calls["n"] == 1:
            raise psycopg.OperationalError("SSL connection has been closed unexpectedly")
        return "ok-after-reconnect"

    result = await session._with_reconnect(op)

    assert result == "ok-after-reconnect"
    assert calls["n"] == 2  # failed once, succeeded on retry
    assert reconnects["n"] == 1  # reconnected exactly once


async def test_non_connection_error_propagates_without_reconnect(monkeypatch):
    session = _make_session()
    reconnects = {"n": 0}

    async def fake_reconnect():
        reconnects["n"] += 1

    monkeypatch.setattr(session, "_reconnect", fake_reconnect)

    async def op():
        raise ValueError("a real bug, not a dropped connection")

    with pytest.raises(ValueError, match="a real bug"):
        await session._with_reconnect(op)
    assert reconnects["n"] == 0  # must NOT reconnect/retry on non-connection errors


async def test_get_session_rehydrates_unknown_id(monkeypatch):
    """After a restart an old conversation_id has no in-memory session; it must be reopened (the
    history lives in Postgres), not 404'd."""
    import sys
    from uuid import uuid4

    # NB: `api.__init__` re-exports the FastAPI instance as `app`, shadowing the submodule
    # for attribute access — so fetch the real module from sys.modules to reach its globals.
    apimod = sys.modules["api.app"]

    cid = uuid4()
    apimod._SESSIONS.pop(cid, None)
    started = {"n": 0}

    async def fake_start(self):  # noqa: ANN001
        started["n"] += 1
        self.app = object()  # sentinel; no real DB

    monkeypatch.setattr(apimod._Session, "start", fake_start)
    try:
        first = await apimod._get_session(cid)
        assert first.conversation_id == cid
        assert apimod._SESSIONS.get(cid) is first
        assert started["n"] == 1  # opened once

        again = await apimod._get_session(cid)
        assert again is first  # reused, not reopened
        assert started["n"] == 1
    finally:
        apimod._SESSIONS.pop(cid, None)


async def test_retry_failure_surfaces_after_reconnect(monkeypatch):
    """If the fresh connection also fails, the error surfaces (no infinite loop)."""
    session = _make_session()

    async def fake_reconnect():
        pass

    monkeypatch.setattr(session, "_reconnect", fake_reconnect)

    async def op():
        raise psycopg.OperationalError("server closed the connection unexpectedly")

    with pytest.raises(psycopg.OperationalError):
        await session._with_reconnect(op)
