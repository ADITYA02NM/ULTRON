"""Revoking a credential must end everything it authorised.

These tests exist because it is easy to revoke a row and believe you have
revoked access. A session row, and the WebSocket a session is holding open,
both outlive `credentials.revoked` unless something explicitly walks them.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from aiohttp import WSCloseCode, test_utils, web

from server.auth import SESSION_COOKIE, add_auth_routes, reset_rate_limits
from server.auth_db import AuthDB
from server.ws_session import SessionWsManager

RP_ID = "localhost"
ORIGIN = "http://localhost:8080"


def _make_app(tmp_db: AuthDB, **extra) -> web.Application:
    app = web.Application()
    app["auth_db"] = tmp_db
    app["auth_rp_id"] = RP_ID
    app["auth_rp_name"] = "ULTRON"
    app["auth_origins"] = [ORIGIN]
    app["auth_secure_cookies"] = False
    app["demo_code"] = ""
    app["session_mgr"] = SessionWsManager()
    for key, value in extra.items():
        app[key] = value
    add_auth_routes(app)
    return app


@pytest.fixture
def tmp_db(tmp_path):
    database = AuthDB(tmp_path / "auth.db")
    yield database
    database.close()


@pytest_asyncio.fixture
async def client(tmp_db):
    reset_rate_limits()
    async with test_utils.TestClient(test_utils.TestServer(_make_app(tmp_db))) as test_client:
        yield test_client


# ── the store ─────────────────────────────────────────────────────────────── #

def test_revoking_a_credential_invalidates_its_sessions(tmp_db):
    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    sid = tmp_db.create_session("c1")
    assert tmp_db.validate_session(sid) is not None

    tmp_db.revoke_credential("c1")

    assert tmp_db.validate_session(sid) is None


def test_a_placeholder_session_survives_its_own_revoked_credential(tmp_db):
    """The demo/skip paths carry sessions on a deliberately REVOKED credential.

    That row exists only so the sessions foreign key holds and holds no key
    material, so it cannot authenticate on its own. If credential revocation
    were enforced blindly, every demo and skip session would be dead on
    arrival — the rig would appear to sign in and then immediately sign out.
    """
    sid = tmp_db.create_session("demo-lan", enforce_credential_fkey=False)

    assert tmp_db.validate_session(sid) is not None


def test_revoke_sessions_for_credential_returns_what_it_ended(tmp_db):
    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    tmp_db.create_session("c1")
    tmp_db.create_session("c1")

    ended = tmp_db.revoke_sessions_for_credential("c1")
    assert len(ended) == 2

    # Idempotent: a second call has nothing left to do.
    assert tmp_db.revoke_sessions_for_credential("c1") == []


def test_revoking_one_credential_leaves_another_alone(tmp_db):
    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    tmp_db.save_credential(cred_id="c2", public_key=b"pk", sign_count=0)
    keeper = tmp_db.create_session("c1")
    doomed = tmp_db.create_session("c2")

    tmp_db.revoke_credential("c2")
    tmp_db.revoke_sessions_for_credential("c2")

    assert tmp_db.validate_session(doomed) is None
    assert tmp_db.validate_session(keeper) is not None


def test_an_expired_session_is_refused(tmp_db):
    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    sid = tmp_db.create_session("c1", ttl=-1)

    assert tmp_db.validate_session(sid) is None


# ── the endpoint ──────────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_revoking_via_the_api_ends_that_credentials_sessions(client, tmp_db):
    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    tmp_db.save_credential(cred_id="c2", public_key=b"pk", sign_count=0)
    mine = tmp_db.create_session("c1")
    doomed = tmp_db.create_session("c2")

    resp = await client.delete("/auth/credentials/c2",
                               cookies={SESSION_COOKIE: mine})
    assert resp.status == 200, await resp.text()
    assert (await resp.json())["sessions_revoked"] == 1

    # The revoked device is out; the operator's own session is untouched.
    assert tmp_db.validate_session(doomed) is None
    assert tmp_db.validate_session(mine) is not None


@pytest.mark.asyncio
async def test_the_revocation_is_recorded_with_its_session_count(client, tmp_db):
    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    tmp_db.save_credential(cred_id="c2", public_key=b"pk", sign_count=0)
    mine = tmp_db.create_session("c1")
    tmp_db.create_session("c2")

    await client.delete("/auth/credentials/c2", cookies={SESSION_COOKIE: mine})

    entry = next(a for a in tmp_db.read_audit() if a["event"] == "credential_revoked")
    assert entry["credential_id"] == "c2"
    assert "sessions_revoked=1" in (entry["detail"] or "")


# ── the socket guard ──────────────────────────────────────────────────────── #

class _FakeWs:
    """Just enough WebSocketResponse to observe a close."""

    def __init__(self) -> None:
        self.closed: tuple | None = None

    async def close(self, code=None, message: bytes = b"") -> None:
        self.closed = (code, message)


class _FakeRequest:
    """Just enough Request for the guard: an app mapping and cookies."""

    def __init__(self, app: dict, cookies: dict) -> None:
        self.app = app
        self.cookies = cookies


@pytest.mark.asyncio
async def test_the_guard_closes_a_socket_once_its_session_is_revoked(tmp_db):
    from server.main import _guard_session

    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    sid = tmp_db.create_session("c1")
    ws, request = _FakeWs(), _FakeRequest(
        {"auth_db": tmp_db, "ws_revalidate_s": 0.01}, {SESSION_COOKIE: sid}
    )

    task = asyncio.create_task(_guard_session(ws, request, "deadbeef"))
    tmp_db.revoke_credential("c1")

    await asyncio.wait_for(task, timeout=5)
    assert ws.closed is not None, "socket outlived the session that opened it"
    assert ws.closed[0] == WSCloseCode.POLICY_VIOLATION


@pytest.mark.asyncio
async def test_the_guard_leaves_a_healthy_socket_connected(tmp_db):
    from server.main import _guard_session

    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    sid = tmp_db.create_session("c1")
    ws, request = _FakeWs(), _FakeRequest(
        {"auth_db": tmp_db, "ws_revalidate_s": 0.01}, {SESSION_COOKIE: sid}
    )

    task = asyncio.create_task(_guard_session(ws, request, "deadbeef"))
    await asyncio.sleep(0.15)
    assert ws.closed is None, "guard closed a socket whose session was still valid"
    task.cancel()


@pytest.mark.asyncio
async def test_the_guard_closes_a_socket_whose_cookie_went_away(tmp_db):
    from server.main import _guard_session

    tmp_db.save_credential(cred_id="c1", public_key=b"pk", sign_count=0)
    ws, request = _FakeWs(), _FakeRequest(
        {"auth_db": tmp_db, "ws_revalidate_s": 0.01}, {}  # cookie cleared
    )

    await asyncio.wait_for(_guard_session(ws, request, "deadbeef"), timeout=5)
    assert ws.closed is not None
