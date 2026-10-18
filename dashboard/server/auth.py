"""ULTRON WebAuthn authentication routes (Pi4 — GOVERNANCE).

Single-owner passkey authentication. No passwords, no biometrics stored.
py_webauthn handles all cryptographic verification.

Route table (all under /auth/):
  POST /auth/setup              token-gated first-credential registration
  POST /auth/register/begin     start registration ceremony
  POST /auth/register/complete  finish registration
  POST /auth/login/begin        start authentication ceremony
  POST /auth/login/complete     finish authentication
  POST /auth/reauth/begin       re-authentication (session refresh)
  POST /auth/reauth/complete    finish re-auth
  POST /auth/logout             end session
  GET  /auth/credentials        list credentials (authenticated)
  DELETE /auth/credentials/{id} revoke a credential (authenticated)
  POST /auth/demo               LAN access-code sign-in (if ULTRON_DEMO_CODE set)
  POST /auth/skip               local skip without a passkey (rehearsal only)
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from collections import defaultdict
from typing import Any

from aiohttp import web

import webauthn
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .auth_db import AuthDB

LOG = logging.getLogger("ultron.auth")

CEREMONY_COOKIE = "ultron_ceremony"
SESSION_COOKIE = "ultron_session"
CEREMONY_TTL = 180  # 3 minutes
SESSION_TTL = 3600  # 1 hour

# ── Rate limiting ─────────────────────────────────────────────────────────── #

_rate: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 300  # 5 minutes
_RATE_MAX = 5
_RATE_SWEEP_AT = 512  # sweep the table once it holds this many sources
_RATE_MAX_SOURCES = 4096  # hard ceiling on tracked sources
_rate_audited: dict[str, float] = {}  # ip -> when we last logged a rejection


def reset_rate_limits() -> None:
    _rate.clear()
    _rate_audited.clear()


def _sweep_rate(now: float) -> None:
    """Drop sources that have been quiet for a full window.

    Without this the table holds one entry per source address forever, so an
    attacker rotating through an IPv6 /64 — or just a busy network — grows it
    without bound.
    """
    stale = [ip for ip, ts in _rate.items()
             if not ts or now - ts[-1] >= _RATE_WINDOW]
    for ip in stale:
        _rate.pop(ip, None)
        _rate_audited.pop(ip, None)
    # Sweeping only helps once sources go quiet. If a flood has many sources
    # active at the same instant, none of them are stale, so evict the coldest
    # until the table is back inside its ceiling.
    overflow = len(_rate) - _RATE_MAX_SOURCES
    if overflow > 0:
        oldest = sorted(_rate, key=lambda ip: _rate[ip][-1] if _rate[ip] else 0.0)
        for ip in oldest[:overflow]:
            _rate.pop(ip, None)
            _rate_audited.pop(ip, None)


def _check_rate(ip: str, auth_db: AuthDB) -> bool:
    now = time.time()
    if len(_rate) >= _RATE_SWEEP_AT:
        _sweep_rate(now)
    recent = [t for t in _rate[ip] if now - t < _RATE_WINDOW]
    _rate[ip] = recent
    if len(recent) >= _RATE_MAX:
        backoff = 2 ** (len(recent) - _RATE_MAX)
        if recent and (now - recent[-1]) < backoff:
            # Record the rejection once per window per source. Writing a row for
            # every attempt turns the audit trail into a disk-fill vector — the
            # attacker gets to choose how much we write.
            if now - _rate_audited.get(ip, 0.0) >= _RATE_WINDOW:
                auth_db.audit("rate_limited", ip=ip)
                _rate_audited[ip] = now
            return False
    recent.append(now)
    return True


def _rate_guard(request: web.Request, auth_db: AuthDB) -> None:
    ip = request.remote or "unknown"
    if not _check_rate(ip, auth_db):
        raise web.HTTPTooManyRequests(text="Rate limited")


# ── Helpers ───────────────────────────────────────────────────────────────── #

def _get_auth_db(request: web.Request) -> AuthDB:
    return request.app["auth_db"]


def _get_rp_id(request: web.Request) -> str:
    return request.app["auth_rp_id"]


def _get_rp_name(request: web.Request) -> str:
    return request.app["auth_rp_name"]


def _get_origins(request: web.Request) -> list[str]:
    return request.app["auth_origins"]


def _secure_cookies(request: web.Request) -> bool:
    return request.app.get("auth_secure_cookies", False)


def _set_ceremony_cookie(
    resp: web.Response, ceremony_id: str,
    *, secure: bool = False,
) -> None:
    resp.set_cookie(
        CEREMONY_COOKIE, ceremony_id,
        max_age=CEREMONY_TTL, httponly=True,
        samesite="Strict", secure=secure, path="/auth/",
    )


def _get_ceremony_id(request: web.Request) -> str:
    cid = request.cookies.get(CEREMONY_COOKIE)
    if not cid:
        raise web.HTTPBadRequest(text="Missing ceremony cookie")
    return cid


def _set_session_cookie(
    resp: web.Response, sid: str,
    *, secure: bool = False,
) -> None:
    resp.set_cookie(
        SESSION_COOKIE, sid,
        max_age=SESSION_TTL, httponly=True,
        samesite="Strict", secure=secure, path="/",
    )


def _clear_session_cookie(resp: web.Response) -> None:
    resp.del_cookie(SESSION_COOKIE, path="/")


def _require_session(request: web.Request) -> str:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        raise web.HTTPUnauthorized(text="No session")
    auth_db = _get_auth_db(request)
    session = auth_db.validate_session(sid)
    if not session:
        raise web.HTTPUnauthorized(text="Invalid or expired session")
    return sid


# ── Setup (token-gated first credential) ─────────────────────────────────── #

def _is_loopback(request: web.Request) -> bool:
    """True when the request came from this machine (localhost-only setup)."""
    return (request.remote or "") in (
        "127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost",
    )


async def handle_setup(request: web.Request) -> web.Response:
    auth_db = _get_auth_db(request)
    _rate_guard(request, auth_db)

    body = await request.json()
    token = str(body.get("token", "") or "")

    if token:
        if not auth_db.consume_enrollment_token(token):
            auth_db.audit("setup_bad_token", ip=request.remote)
            raise web.HTTPForbidden(text="Invalid or expired enrollment token")
        auth_db.audit("setup_token_consumed", ip=request.remote)
    elif auth_db.has_owner() or not _is_loopback(request):
        # No token supplied: allowed only for the FIRST owner from this very
        # machine. Any later registration, or any request arriving from the
        # network, still needs an enrollment token.
        auth_db.audit("setup_no_token_refused", ip=request.remote)
        raise web.HTTPForbidden(text="Enrollment token required")
    else:
        auth_db.audit("setup_local_first_owner", ip=request.remote)


    rp_id = _get_rp_id(request)
    rp_name = _get_rp_name(request)

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=b"ultron-owner",
        user_name="owner",
        user_display_name="ULTRON Owner",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )

    ceremony_id = secrets.token_urlsafe(32)
    auth_db.store_challenge(
        ceremony_id, bytes_to_base64url(options.challenge),
        "registration", CEREMONY_TTL,
    )

    resp = web.Response(
        text=webauthn.options_to_json(options),
        content_type="application/json",
    )
    _set_ceremony_cookie(resp, ceremony_id, secure=_secure_cookies(request))
    return resp


async def handle_setup_complete(request: web.Request) -> web.Response:
    auth_db = _get_auth_db(request)
    _rate_guard(request, auth_db)
    ceremony_id = _get_ceremony_id(request)

    challenge_b64 = auth_db.consume_challenge(ceremony_id)
    if not challenge_b64:
        auth_db.audit("setup_challenge_invalid", ip=request.remote)
        raise web.HTTPBadRequest(text="Invalid or expired challenge")

    body = await request.json()

    try:
        verification = webauthn.verify_registration_response(
            credential=body,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_origin=_get_origins(request),
            expected_rp_id=_get_rp_id(request),
            require_user_verification=True,
        )
    except Exception as e:
        auth_db.audit("setup_verify_failed", ip=request.remote, detail=str(e))
        # The detail goes to the audit trail, not to the caller: raw exception
        # text leaks library internals and filesystem paths.
        raise web.HTTPBadRequest(text="Verification failed") from e

    cred_id = bytes_to_base64url(verification.credential_id)
    auth_db.save_credential(
        cred_id=cred_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        transports=json.dumps([t.value for t in (verification.credential_backed_up and [] or [])]) if hasattr(verification, 'credential_backed_up') else None,
        device_type=verification.credential_device_type if hasattr(verification, 'credential_device_type') else None,
        backed_up=getattr(verification, 'credential_backed_up', False),
        aaguid=str(getattr(verification, 'aaguid', '')),
    )
    auth_db.audit("credential_registered", ip=request.remote, credential_id=cred_id)

    sid = auth_db.create_session(cred_id, ip=request.remote, ttl=SESSION_TTL)
    resp = web.json_response({"status": "ok", "credential_id": cred_id})
    _set_session_cookie(resp, sid, secure=_secure_cookies(request))
    return resp


# ── Registration (add credential — authenticated) ────────────────────────── #

async def handle_register_begin(request: web.Request) -> web.Response:
    _require_session(request)
    auth_db = _get_auth_db(request)
    _rate_guard(request, auth_db)

    existing = auth_db.list_credentials()
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.id))
        for c in existing if not c.revoked
    ]

    options = webauthn.generate_registration_options(
        rp_id=_get_rp_id(request),
        rp_name=_get_rp_name(request),
        user_id=b"ultron-owner",
        user_name="owner",
        user_display_name="ULTRON Owner",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude,
    )

    ceremony_id = secrets.token_urlsafe(32)
    auth_db.store_challenge(
        ceremony_id, bytes_to_base64url(options.challenge),
        "registration", CEREMONY_TTL,
    )

    resp = web.Response(
        text=webauthn.options_to_json(options),
        content_type="application/json",
    )
    _set_ceremony_cookie(resp, ceremony_id, secure=_secure_cookies(request))
    return resp


async def handle_register_complete(request: web.Request) -> web.Response:
    _require_session(request)
    auth_db = _get_auth_db(request)
    _rate_guard(request, auth_db)
    ceremony_id = _get_ceremony_id(request)

    challenge_b64 = auth_db.consume_challenge(ceremony_id)
    if not challenge_b64:
        auth_db.audit("register_challenge_invalid", ip=request.remote)
        raise web.HTTPBadRequest(text="Invalid or expired challenge")

    body = await request.json()

    try:
        verification = webauthn.verify_registration_response(
            credential=body,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_origin=_get_origins(request),
            expected_rp_id=_get_rp_id(request),
            require_user_verification=True,
        )
    except Exception as e:
        auth_db.audit("register_verify_failed", ip=request.remote, detail=str(e))
        raise web.HTTPBadRequest(text="Verification failed") from e

    cred_id = bytes_to_base64url(verification.credential_id)
    auth_db.save_credential(
        cred_id=cred_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        device_type=verification.credential_device_type if hasattr(verification, 'credential_device_type') else None,
        backed_up=getattr(verification, 'credential_backed_up', False),
        aaguid=str(getattr(verification, 'aaguid', '')),
    )
    auth_db.audit("credential_registered", ip=request.remote, credential_id=cred_id)
    return web.json_response({"status": "ok", "credential_id": cred_id})


# ── Login ─────────────────────────────────────────────────────────────────── #

async def handle_login_begin(request: web.Request) -> web.Response:
    auth_db = _get_auth_db(request)
    _rate_guard(request, auth_db)

    creds = auth_db.list_credentials()
    allow = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.id))
        for c in creds if not c.revoked
    ]

    if not allow:
        raise web.HTTPForbidden(text="No credentials registered")

    options = webauthn.generate_authentication_options(
        rp_id=_get_rp_id(request),
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    ceremony_id = secrets.token_urlsafe(32)
    auth_db.store_challenge(
        ceremony_id, bytes_to_base64url(options.challenge),
        "authentication", CEREMONY_TTL,
    )

    resp = web.Response(
        text=webauthn.options_to_json(options),
        content_type="application/json",
    )
    _set_ceremony_cookie(resp, ceremony_id, secure=_secure_cookies(request))
    return resp


async def handle_login_complete(request: web.Request) -> web.Response:
    auth_db = _get_auth_db(request)
    _rate_guard(request, auth_db)
    ceremony_id = _get_ceremony_id(request)
    ip = request.remote or "unknown"

    body = await request.json()

    # Step 1: Parse credential ID
    raw_id = body.get("rawId") or body.get("id", "")

    # Step 2: Look up among non-revoked credentials — reject unknown FIRST
    cred = auth_db.get_credential(raw_id)
    if not cred:
        auth_db.audit("unknown_credential", ip=ip, credential_id=raw_id)
        raise web.HTTPUnauthorized(text="Unknown credential")
    if cred.revoked:
        auth_db.audit("revoked_credential_used", ip=ip, credential_id=raw_id)
        raise web.HTTPUnauthorized(text="Credential revoked")

    # Step 3: Consume the challenge (single-use, bound to ceremony)
    challenge_b64 = auth_db.consume_challenge(ceremony_id)
    if not challenge_b64:
        auth_db.audit("login_challenge_invalid", ip=ip, credential_id=raw_id)
        raise web.HTTPBadRequest(text="Invalid or expired challenge")

    # Step 4: py_webauthn verify
    try:
        verification = webauthn.verify_authentication_response(
            credential=body,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_origin=_get_origins(request),
            expected_rp_id=_get_rp_id(request),
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
    except Exception as e:
        auth_db.audit("login_verify_failed", ip=ip,
                      credential_id=raw_id, detail=str(e))
        raise web.HTTPUnauthorized(text="Verification failed") from e

    # Step 5: Counter rule
    new_count = verification.new_sign_count
    if cred.sign_count > 0 and new_count > 0 and new_count <= cred.sign_count:
        auth_db.audit("counter_regression", ip=ip, credential_id=raw_id,
                      detail=f"expected>{cred.sign_count}, got={new_count}")
        raise web.HTTPUnauthorized(text="Authenticator counter regression")
    auth_db.update_sign_count(raw_id, new_count)

    # Step 6: Create session
    sid = auth_db.create_session(raw_id, ip=ip, ttl=SESSION_TTL)
    auth_db.audit("login_success", ip=ip, credential_id=raw_id)

    resp = web.json_response({"status": "ok"})
    _set_session_cookie(resp, sid, secure=_secure_cookies(request))
    return resp


# ── Re-auth ───────────────────────────────────────────────────────────────── #

async def handle_reauth_begin(request: web.Request) -> web.Response:
    # Same as login_begin (uses same credentials)
    return await handle_login_begin(request)


async def handle_reauth_complete(request: web.Request) -> web.Response:
    # Same verification as login_complete
    return await handle_login_complete(request)


# ── Logout ────────────────────────────────────────────────────────────────── #

async def handle_logout(request: web.Request) -> web.Response:
    sid = request.cookies.get(SESSION_COOKIE)
    auth_db = _get_auth_db(request)
    if sid:
        auth_db.revoke_session(sid)
        auth_db.audit("logout", ip=request.remote)
        # Close all WebSockets for this session
        session_mgr = request.app.get("session_mgr")
        if session_mgr:
            sid_hash = hashlib.sha256(sid.encode()).hexdigest()
            await session_mgr.close_session_sockets(sid_hash)
    resp = web.json_response({"status": "ok"})
    _clear_session_cookie(resp)
    return resp


# ── Credential management ─────────────────────────────────────────────────── #

async def handle_list_credentials(request: web.Request) -> web.Response:
    _require_session(request)
    auth_db = _get_auth_db(request)
    creds = auth_db.list_credentials()
    return web.json_response([
        {
            "id": c.id,
            "created_at": c.created_at,
            "last_used_at": c.last_used_at,
            "revoked": c.revoked,
            "device_type": c.device_type,
            "backed_up": c.backed_up,
            "sign_count": c.sign_count,
        }
        for c in creds
    ])


async def handle_revoke_credential(request: web.Request) -> web.Response:
    _require_session(request)
    auth_db = _get_auth_db(request)
    cred_id = request.match_info["id"]

    if auth_db.count_non_revoked() <= 1:
        cred = auth_db.get_credential_non_revoked(cred_id)
        if cred:
            raise web.HTTPConflict(text="Cannot revoke last credential")

    if not auth_db.revoke_credential(cred_id):
        raise web.HTTPNotFound(text="Credential not found or already revoked")

    # Revoking the credential must also end what it authorised. Otherwise the
    # device you just revoked keeps its dashboard session, and any socket it
    # holds keeps streaming, until the session TTL happens to expire.
    ended = auth_db.revoke_sessions_for_credential(cred_id)
    session_mgr = request.app.get("session_mgr")
    if session_mgr is not None:
        for sid_hash in ended:
            await session_mgr.close_session_sockets(sid_hash)

    auth_db.audit("credential_revoked", ip=request.remote, credential_id=cred_id,
                  detail=f"sessions_revoked={len(ended)}")
    return web.json_response({"status": "ok", "sessions_revoked": len(ended)})


# ── Demo / LAN access + skip (optional escape hatches) ───────────────────── #

DEMO_CREDENTIAL_ID = "demo-lan"
SKIP_CREDENTIAL_ID = "skip-local"


def _demo_code(request: web.Request) -> str:
    return str(request.app.get("demo_code") or "")


def _issue_session(
    request: web.Request, auth_db: AuthDB, placeholder_id: str,
    *, event: str,
) -> str:
    """Mint a session for the first live credential, or a placeholder row.

    The placeholder path is why create_session() takes
    ``enforce_credential_fkey=False``: a session can exist with no passkey.
    """
    principals = [c.id for c in auth_db.list_credentials() if not c.revoked]
    if principals:
        sid = auth_db.create_session(
            principals[0], ip=request.remote, ttl=SESSION_TTL,
        )
        auth_db.audit(event, ip=request.remote, credential_id=placeholder_id)
    else:
        sid = auth_db.create_session(
            placeholder_id, ip=request.remote, ttl=SESSION_TTL,
            enforce_credential_fkey=False,
        )
        auth_db.audit(f"{event}_no_owner", ip=request.remote,
                      credential_id=placeholder_id)
        LOG.warning("%s session issued with no registered passkey", event)
    return sid


async def handle_demo(request: web.Request) -> web.Response:
    """Sign in with the printed LAN access code (demo rig only)."""
    code_cfg = _demo_code(request)
    if not code_cfg:
        raise web.HTTPNotFound(text="LAN access code not configured")

    auth_db = _get_auth_db(request)
    _rate_guard(request, auth_db)

    try:
        body = await request.json()
    except ValueError as e:
        raise web.HTTPBadRequest(text="JSON body required") from e

    given = str(body.get("code", ""))
    if not given or not secrets.compare_digest(given, code_cfg):
        auth_db.audit("demo_denied", ip=request.remote)
        raise web.HTTPForbidden(text="Wrong access code")

    sid = _issue_session(request, auth_db, DEMO_CREDENTIAL_ID, event="demo_login")
    resp = web.json_response({"ok": True, "mode": "demo-code"})
    _set_session_cookie(resp, sid, secure=_secure_cookies(request))
    LOG.info("LAN demo session issued to %s", request.remote)
    return resp


async def handle_skip(request: web.Request) -> web.Response:
    """Mint a local session without a passkey (rehearsal escape hatch)."""
    auth_db = _get_auth_db(request)
    _rate_guard(request, auth_db)

    sid = _issue_session(request, auth_db, SKIP_CREDENTIAL_ID, event="skip_login")
    resp = web.json_response({"ok": True, "mode": "skip"})
    _set_session_cookie(resp, sid, secure=_secure_cookies(request))
    LOG.info("skip session issued to %s", request.remote)
    return resp


# ── Auth status ───────────────────────────────────────────────────────────── #

async def handle_auth_status(request: web.Request) -> web.Response:
    auth_db = _get_auth_db(request)
    has_owner = auth_db.has_owner()
    sid = request.cookies.get(SESSION_COOKIE)
    authenticated = False
    if sid:
        session = auth_db.validate_session(sid)
        authenticated = session is not None
    return web.json_response({
        "has_owner": has_owner,
        "authenticated": authenticated,
        "show_register": not has_owner,
    })


# ── Route registration ───────────────────────────────────────────────────── #

def add_auth_routes(app: web.Application) -> None:
    app.add_routes([
        web.post("/auth/setup", handle_setup),
        web.post("/auth/setup/complete", handle_setup_complete),
        web.post("/auth/register/begin", handle_register_begin),
        web.post("/auth/register/complete", handle_register_complete),
        web.post("/auth/login/begin", handle_login_begin),
        web.post("/auth/login/complete", handle_login_complete),
        web.post("/auth/reauth/begin", handle_reauth_begin),
        web.post("/auth/reauth/complete", handle_reauth_complete),
        web.post("/auth/logout", handle_logout),
        web.get("/auth/credentials", handle_list_credentials),
        web.delete("/auth/credentials/{id}", handle_revoke_credential),
        web.get("/auth/status", handle_auth_status),
        web.post("/auth/demo", handle_demo),
        web.post("/auth/skip", handle_skip),
    ])
