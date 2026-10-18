"""The push path is the one way alert content can leave the LAN.

Two properties matter, and neither is visible from reading `run()`:

  1. Off by default, and off means *not dialled*. `push_band()` returns before
     it builds a URL when no topic is configured, so the appliance's zero-cloud
     claim holds for every operator who never asked for push.
  2. A dead relay costs us a notification, never the record. `urllib.error`
     raises `URLError` (and `HTTPError` for a 4xx/5xx), and both derive from
     `OSError` — the only thing caught. This node is the sole writer of the
     evidence vault; push is a courtesy on top of it.

The transport is a plain HTTP POST to an ntfy-compatible server, so these tests
read the request the node would have sent rather than mocking a client library.
That is the whole contract with the server, so it is worth asserting exactly.
"""

from __future__ import annotations

import argparse
import io
import urllib.error
import urllib.request

import pytest

import alert_manager

BODY = "Risk band is now RED.\nOpen the dashboard to review and acknowledge."


def _args(**over: object) -> argparse.Namespace:
    """A namespace shaped like the CLI defaults in alert_manager.main()."""
    base = dict(
        dry_run=False,
        push_url="https://ntfy.sh",
        push_topic=None,
        push_bands="RED,PURPLE",
    )
    base.update(over)
    return argparse.Namespace(**base)


class Recorder:
    """Stands in for urlopen, keeping the Request and answering a body."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout=None):
        self.requests.append(request)
        # push_band uses `with urlopen(...) as resp`, so this must be a context
        # manager. BytesIO is one, which keeps the fake honest.
        return io.BytesIO(b"ok")


def _forbid_dial(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("urlopen must not be called here")

    monkeypatch.setattr(urllib.request, "urlopen", explode)


# ---------------------------------------------------------------- suppression


def test_without_a_topic_nothing_is_dialled(monkeypatch):
    _forbid_dial(monkeypatch)
    alert_manager.push_band(_args(), "RED", "ULTRON RED", BODY)


def test_dry_run_never_dials_even_with_a_topic(monkeypatch, caplog):
    _forbid_dial(monkeypatch)
    with caplog.at_level("INFO", logger="ultron.alert"):
        alert_manager.push_band(_args(push_topic="ultron-test", dry_run=True),
                                 "RED", "s", "b")
    assert "[push suppressed]" in caplog.text


# ------------------------------------------------------------------ the request


def test_the_request_is_well_formed(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(urllib.request, "urlopen", rec)

    alert_manager.push_band(_args(push_topic="ultron-test"), "RED", "ULTRON RED", BODY)

    assert len(rec.requests) == 1
    req = rec.requests[0]
    assert req.full_url == "https://ntfy.sh/ultron-test"
    assert req.get_method() == "POST"
    assert req.data == BODY.encode("utf-8")
    assert req.get_header("Title") == "ULTRON RED"
    assert req.get_header("Priority") == "high"
    assert req.get_header("Tags") == "warning"


def test_purple_escalates_the_urgency(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(urllib.request, "urlopen", rec)

    alert_manager.push_band(_args(push_topic="ultron-test"), "PURPLE", "ULTRON PURPLE", BODY)

    req = rec.requests[0]
    assert req.get_header("Priority") == "urgent"
    assert req.get_header("Tags") == "rotating_light"


def test_a_topic_is_percent_encoded(monkeypatch):
    """A topic is operator-supplied text and lands in a URL path."""
    rec = Recorder()
    monkeypatch.setattr(urllib.request, "urlopen", rec)

    alert_manager.push_band(_args(push_topic="two words"), "RED", "s", "b")

    assert rec.requests[0].full_url == "https://ntfy.sh/two%20words"


def test_a_self_hosted_server_keeps_its_path_and_loses_its_slash(monkeypatch):
    """Pointing PUSH_URL at a relay on the LAN is the way to keep alert content
    on the LAN; the trailing slash must not double up."""
    rec = Recorder()
    monkeypatch.setattr(urllib.request, "urlopen", rec)

    alert_manager.push_band(
        _args(push_url="http://10.0.0.5:8080/", push_topic="ultron"), "RED", "s", "b"
    )

    assert rec.requests[0].full_url == "http://10.0.0.5:8080/ultron"


# -------------------------------------------------------------------- failure


def test_a_dead_relay_is_logged_and_never_raised(monkeypatch, caplog):
    def dead(*_a: object, **_k: object) -> None:
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(urllib.request, "urlopen", dead)
    with caplog.at_level("ERROR", logger="ultron.alert"):
        alert_manager.push_band(_args(push_topic="ultron-test"), "RED", "s", "b")
    assert "could not push notification" in caplog.text


def test_a_rejected_topic_is_logged_and_never_raised(monkeypatch, caplog):
    """A 404 from the relay arrives as HTTPError, which is an OSError too."""

    def rejected(*_a: object, **_k: object) -> None:
        raise urllib.error.HTTPError(
            "https://ntfy.sh/ultron-test", 404, "Not Found", {}, None
        )

    monkeypatch.setattr(urllib.request, "urlopen", rejected)
    with caplog.at_level("ERROR", logger="ultron.alert"):
        alert_manager.push_band(_args(push_topic="ultron-test"), "RED", "s", "b")
    assert "could not push notification" in caplog.text
