"""Auth escape hatches: the LAN access code (/auth/demo) and skip (/auth/skip).

These paths exist so a phone or a second laptop can reach the dashboard during a
demo without a passkey: passkeys are bound to the RP id, so a LAN browser cannot
use one. Both paths are rate-limited and audited like the passkey flows.
"""
import pytest
import pytest_asyncio
from aiohttp import test_utils, web

from server.auth import SESSION_COOKIE, add_auth_routes, reset_rate_limits
from server.auth_db import AuthDB
from server.config import Config, ConfigError, _validate
from server.ws_session import SessionWsManager

RP_ID = "localhost"
ORIGIN = "http://localhost:8080"
DEMO_CODE = "BEEF-CAFE"


def _make_app(tmp_db, *, demo_code: str = ""):
    app = web.Application()
    app["auth_db"] = tmp_db
    app["auth_rp_id"] = RP_ID
    app["auth_rp_name"] = "ULTRON"
    app["auth_origins"] = [ORIGIN]
    app["auth_secure_cookies"] = False
    app["demo_code"] = demo_code
    app["session_mgr"] = SessionWsManager()
    add_auth_routes(app)
    return app


@pytest_asyncio.fixture
async def tmp_db(tmp_path):
    db = AuthDB(tmp_path / "auth.db")
    yield db
    db.close()


@pytest_asyncio.fixture
async def client(tmp_db):
    reset_rate_limits()
    async with test_utils.TestClient(test_utils.TestServer(_make_app(tmp_db))) as c:
        yield c


@pytest_asyncio.fixture
async def demo_client(tmp_db):
    reset_rate_limits()
    async with test_utils.TestClient(
        test_utils.TestServer(_make_app(tmp_db, demo_code=DEMO_CODE))
    ) as c:
        yield c


def _events(db: AuthDB) -> list[str]:
    return [a["event"] for a in db.read_audit()]


@pytest.mark.asyncio
async def test_skip_mints_session_with_no_owner(client, tmp_db):
    assert tmp_db.has_owner() is False

    r = await client.post("/auth/skip", json={})
    assert r.status == 200, await r.text()
    assert (await r.json())["mode"] == "skip"

    sid = r.cookies[SESSION_COOKIE].value
    assert tmp_db.validate_session(sid) is not None
    # The placeholder credential stays revoked, so there is still no owner.
    assert tmp_db.has_owner() is False
    assert "skip_login_no_owner" in _events(tmp_db)


@pytest.mark.asyncio
async def test_skip_then_status_is_authenticated(client):
    r = await client.post("/auth/skip", json={})
    sid = r.cookies[SESSION_COOKIE].value

    st = await client.get("/auth/status", cookies={SESSION_COOKIE: sid})
    body = await st.json()
    assert body["authenticated"] is True
    assert body["has_owner"] is False


@pytest.mark.asyncio
async def test_demo_code_accepted(demo_client, tmp_db):
    r = await demo_client.post("/auth/demo", json={"code": DEMO_CODE})
    assert r.status == 200, await r.text()
    assert (await r.json())["mode"] == "demo-code"

    sid = r.cookies[SESSION_COOKIE].value
    assert tmp_db.validate_session(sid) is not None
    assert "demo_login_no_owner" in _events(tmp_db)


@pytest.mark.asyncio
async def test_demo_code_rejected(demo_client, tmp_db):
    r = await demo_client.post("/auth/demo", json={"code": "wrong"})
    assert r.status == 403
    assert "demo_denied" in _events(tmp_db)


@pytest.mark.asyncio
async def test_demo_rejected_when_disabled(client):
    r = await client.post("/auth/demo", json={"code": DEMO_CODE})
    assert r.status == 404


@pytest.mark.asyncio
async def test_status_reports_show_register(client):
    # No owner yet -> the UI offers registration.
    body = await (await client.get("/auth/status")).json()
    assert body["show_register"] is True
    assert body["has_owner"] is False


# --- config: LAN origins (the demo-rig escape hatch) ----------------------- #

def test_lan_origin_rejected_by_default():
    cfg = Config(origins=["http://10.10.8.97:8081"])
    with pytest.raises(ConfigError):
        _validate(cfg)


def test_lan_origin_allowed_for_the_demo_rig():
    cfg = Config(origins=["http://10.10.8.97:8081"], allow_lan=True, demo_code="X")
    _validate(cfg)  # must not raise


def test_localhost_origins_still_allowed_without_allow_lan():
    cfg = Config(origins=["http://localhost:5173", "http://127.0.0.1:8080"])
    _validate(cfg)  # must not raise


@pytest.mark.asyncio
async def test_setup_without_token_refused_once_owner_exists(client, tmp_db):
    """Tokenless setup is only for the FIRST owner, from this machine."""
    tmp_db.save_credential(cred_id="owner-1", public_key=b"pk", sign_count=0)
    assert tmp_db.has_owner() is True
    r = await client.post("/auth/setup", json={})
    assert r.status == 403, await r.text()
    assert "setup_no_token_refused" in _events(tmp_db)


@pytest.mark.asyncio
async def test_setup_with_empty_token_is_not_a_bad_token(client, tmp_db):
    """An empty token must NOT be reported as an invalid token."""
    r = await client.post("/auth/setup", json={"token": ""})
    assert "setup_bad_token" not in _events(tmp_db)
