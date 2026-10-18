"""Hardening checks: cross-site POSTs, and the rate limiter's own footprint.

Both of these are ways the dashboard could be turned against itself — one by a
third-party page, one by an attacker deciding how much we write to disk.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from aiohttp import test_utils

from server import auth as auth_mod
from server.auth_db import AuthDB
from server.config import Config
from server.main import create_app

ALLOWED = "http://localhost:8080"


@pytest.fixture
def tmp_db(tmp_path):
    database = AuthDB(tmp_path / "auth.db")
    yield database
    database.close()


@pytest_asyncio.fixture
async def guarded_client(tmp_path):
    """A real create_app(), so the middleware is exercised as wired."""
    auth_mod.reset_rate_limits()
    app = create_app(Config(auth_db=tmp_path / "auth.db", origins=[ALLOWED]))
    async with test_utils.TestClient(test_utils.TestServer(app)) as client:
        yield client


# ── cross-site state-changing requests ────────────────────────────────────── #

@pytest.mark.asyncio
async def test_cross_origin_post_is_refused(guarded_client):
    """A page on another origin must not be able to POST here.

    /auth/skip needs no cookie at all, so without this check any site could
    mint itself a session in the operator's browser.
    """
    resp = await guarded_client.post(
        "/auth/skip", json={}, headers={"Origin": "http://evil.example"},
    )
    assert resp.status == 403, await resp.text()


@pytest.mark.asyncio
async def test_same_origin_post_is_allowed(guarded_client):
    resp = await guarded_client.post(
        "/auth/skip", json={}, headers={"Origin": ALLOWED},
    )
    assert resp.status == 200, await resp.text()


@pytest.mark.asyncio
async def test_a_post_with_no_origin_is_still_allowed(guarded_client):
    """curl, the CLI and the test client send no Origin and are not CSRF."""
    resp = await guarded_client.post("/auth/skip", json={})
    assert resp.status == 200, await resp.text()


@pytest.mark.asyncio
async def test_cross_origin_get_is_not_blocked(guarded_client):
    """Only state-changing methods are guarded; GET carries no side effect."""
    resp = await guarded_client.get(
        "/healthz", headers={"Origin": "http://evil.example"},
    )
    assert resp.status == 200, await resp.text()


# ── the rate limiter's footprint ──────────────────────────────────────────── #

def test_repeat_rejections_are_logged_once_per_window(tmp_db):
    """A refused request must not be able to write an audit row each time.

    Otherwise the audit trail — the very thing that records the attack — is the
    thing the attack fills up.
    """
    auth_mod.reset_rate_limits()
    ip = "10.0.0.9"
    for _ in range(auth_mod._RATE_MAX):
        assert auth_mod._check_rate(ip, tmp_db) is True

    assert auth_mod._check_rate(ip, tmp_db) is False
    assert auth_mod._check_rate(ip, tmp_db) is False

    events = [a["event"] for a in tmp_db.read_audit()]
    assert events.count("rate_limited") == 1


def test_the_rate_table_is_capped(tmp_db):
    """Source addresses rotate; the table must not follow them forever."""
    auth_mod.reset_rate_limits()
    for i in range(auth_mod._RATE_MAX_SOURCES + 500):
        auth_mod._check_rate(f"10.0.{(i // 256) % 256}.{i % 256}", tmp_db)

    assert len(auth_mod._rate) <= auth_mod._RATE_MAX_SOURCES + 1


def test_reset_clears_both_tables(tmp_db):
    auth_mod.reset_rate_limits()
    auth_mod._check_rate("10.1.1.1", tmp_db)
    auth_mod.reset_rate_limits()

    assert auth_mod._rate == {}
    assert auth_mod._rate_audited == {}
