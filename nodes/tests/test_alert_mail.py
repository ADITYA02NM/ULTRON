"""The mail path is a security boundary as much as a feature.

Two properties matter and neither is visible from reading `run()`:

  1. The password does not leave the process before the connection is
     encrypted *and the relay has proved who it is*. `smtplib.starttls()` with
     no context uses `ssl._create_stdlib_context()`, which verifies nothing —
     no certificate check, no hostname check. Ordering it correctly against a
     context-free upgrade would still be handing an app password to whoever
     answered the socket.
  2. A dead relay costs us a notification, never the record. This node is the
     only writer of the evidence vault; mail is a courtesy on top.

The last test drives a real STARTTLS server rather than a mock, because
ordering is only real if there is an actual handshake to order it against.
"""

from __future__ import annotations

import argparse
import shutil
import smtplib
import socket
import ssl
import subprocess

import pytest

import alert_manager

OPENSSL = shutil.which("openssl")


def _args(**over: object) -> argparse.Namespace:
    """A namespace shaped like the CLI defaults in alert_manager.main()."""
    base = dict(
        db=":memory:",
        dry_run=False,
        smtp_host=None,
        smtp_port=587,
        smtp_user=None,
        smtp_pass=None,
        mail_from="ultron@localhost",
        mail_to=["ops@example.test"],
    )
    base.update(over)
    return argparse.Namespace(**base)


def _forbid_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("smtplib.SMTP must not be constructed here")

    monkeypatch.setattr(smtplib, "SMTP", explode)


# ---------------------------------------------------------------- suppression


def test_without_a_relay_we_do_not_even_dial(monkeypatch, caplog):
    _forbid_connection(monkeypatch)
    with caplog.at_level("INFO", logger="ultron.alert"):
        alert_manager.send_mail(_args(), "ULTRON RED", "body")
    assert "[mail suppressed]" in caplog.text


def test_dry_run_never_connects_even_with_a_host(monkeypatch):
    _forbid_connection(monkeypatch)
    alert_manager.send_mail(
        _args(smtp_host="smtp.example.test", dry_run=True), "ULTRON RED", "body"
    )


# ------------------------------------------------------------------- ordering


def test_the_password_waits_for_a_verified_tls_upgrade(monkeypatch):
    seen: list[tuple] = []

    class FakeSmtp:
        def __init__(self, host, port, timeout=None):
            seen.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def starttls(self, context=None):
            seen.append(("starttls", context))

        def login(self, user, password):
            seen.append(("login", user))

        def send_message(self, msg):
            seen.append(("send", msg["Subject"], msg["To"]))

    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    alert_manager.send_mail(
        _args(
            smtp_host="smtp.example.test",
            smtp_user="ops@example.test",
            smtp_pass="app-password",
        ),
        "ULTRON RED",
        "Risk band is now RED.",
    )

    assert [call[0] for call in seen] == ["connect", "starttls", "login", "send"]
    assert seen[-1][2] == "ops@example.test"

    context = seen[1][1]
    assert context is not None, (
        "starttls() was given no context; the stdlib default verifies no "
        "certificate and no hostname, so the relay is unauthenticated"
    )
    assert context.check_hostname, "the relay's hostname must be checked"
    assert context.verify_mode == ssl.CERT_REQUIRED, "the relay's certificate must be verified"


def test_an_unauthenticated_relay_is_used_without_a_login(monkeypatch):
    """A LAN relay with no AUTH is a supported shape: connect and send."""
    seen: list[str] = []

    class FakeSmtp:
        def __init__(self, *_a, **_k):
            seen.append("connect")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def starttls(self, context=None):
            seen.append("starttls")

        def login(self, *_a):
            raise AssertionError("must not log in when no user is configured")

        def send_message(self, _msg):
            seen.append("send")

    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    alert_manager.send_mail(_args(smtp_host="smtp.example.test"), "s", "b")
    assert seen == ["connect", "send"]


# -------------------------------------------------------------------- failure


def test_a_dead_relay_is_logged_and_never_raised(monkeypatch, caplog):
    class Dead:
        def __init__(self, *_a, **_k):
            raise OSError("Connection refused")

    monkeypatch.setattr(smtplib, "SMTP", Dead)
    with caplog.at_level("ERROR", logger="ultron.alert"):
        alert_manager.send_mail(_args(smtp_host="smtp.example.test"), "s", "b")
    assert "could not send notification" in caplog.text


def test_a_rejected_password_is_logged_and_never_raised(monkeypatch, caplog):
    """SMTPAuthenticationError derives from OSError, so a bad app password is a
    log line, not a crash. That is deliberate: a failed notification must not
    stop the vault being written."""

    class Rejecting:
        def __init__(self, *_a, **_k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def starttls(self, context=None):
            pass

        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

        def send_message(self, _msg):
            raise AssertionError("must not reach send after a failed login")

    monkeypatch.setattr(smtplib, "SMTP", Rejecting)
    with caplog.at_level("ERROR", logger="ultron.alert"):
        alert_manager.send_mail(
            _args(smtp_host="smtp.example.test", smtp_user="u", smtp_pass="wrong"),
            "s",
            "b",
        )
    assert "could not send notification" in caplog.text


# ------------------------------------------------------------------ end to end


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _throwaway_cert(tmp_path) -> tuple[object, object]:
    cert = tmp_path / "relay.pem"
    key = tmp_path / "relay.key"
    subprocess.run(
        [
            OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


@pytest.mark.skipif(OPENSSL is None, reason="needs openssl to mint a throwaway certificate")
def test_a_real_starttls_relay_delivers_the_notification(tmp_path, monkeypatch):
    from aiosmtpd.controller import Controller
    from aiosmtpd.smtp import AuthResult, LoginPassword

    cert, key = _throwaway_cert(tmp_path)
    delivered = []

    class Sink:
        async def handle_DATA(self, server, session, envelope):
            delivered.append(envelope)
            return "250 Message accepted for delivery"

    def authenticate(server, session, envelope, mechanism, auth_data):
        if (
            isinstance(auth_data, LoginPassword)
            and auth_data.login == b"ops"
            and auth_data.password == b"app-password"
        ):
            return AuthResult(success=True)
        return AuthResult(success=False)

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(cert), str(key))

    port = _free_port()
    controller = Controller(
        Sink(),
        hostname="127.0.0.1",
        port=port,
        tls_context=server_context,
        require_starttls=True,
        auth_required=True,
        auth_require_tls=True,      # no AUTH before STARTTLS, like a real relay
        authenticator=authenticate,
    )
    controller.start()
    try:
        # The client verifies the relay now, so the throwaway cert has to be
        # trusted for the duration of the test.
        monkeypatch.setenv("SSL_CERT_FILE", str(cert))
        alert_manager.send_mail(
            _args(
                smtp_host="127.0.0.1",
                smtp_port=port,
                smtp_user="ops",
                smtp_pass="app-password",
                mail_to=["operator@example.test"],
            ),
            "ULTRON RED",
            "Risk band is now RED.",
        )
    finally:
        controller.stop()

    assert len(delivered) == 1, "the relay never accepted a message"
    assert delivered[0].rcpt_tos == ["operator@example.test"]

    raw = delivered[0].content
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    assert "Subject: ULTRON RED" in text
    assert "Risk band is now RED." in text
