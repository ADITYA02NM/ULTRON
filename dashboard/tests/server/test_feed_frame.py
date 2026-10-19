"""The panel frame the feed publishes.

The indicator on the shelf is fed from the broker, and it can only show what
the broker carries. `ultron/risk/score` and `ultron/risk/band` are two halves
of a number and a name; they say nothing about how many alerts are open or
what the newest one was, so a board subscribed to those alone sits next to a
console that shows an alert the panel cannot see.

`ultron/risk/frame` is the whole panel in one object -- the same shape
nodes/pi4/risk_engine.py writes down the serial link on the real rig. These
tests pin that shape, because a field quietly renamed here shows up as a
blank line on the shelf rather than as a failure anywhere.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# tests/server/test_feed_frame.py -> tests/server -> tests -> dashboard -> repo
_REPO = Path(__file__).resolve().parents[3]
_FEED = _REPO / "dashboard" / "tools" / "mock_feed.py"


def _load() -> object:
    """mock_feed.py is a script, not part of a package, so load it by path."""
    spec = importlib.util.spec_from_file_location("mock_feed", _FEED)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mock_feed() -> object:
    return _load()


def _feed(mock_feed: object, **attrs: object) -> tuple[object, list[tuple[str, object, bool]]]:
    """A Feed with no broker behind it, recording every publish it makes."""
    sent: list[tuple[str, object, bool]] = []

    feed = object.__new__(mock_feed.Feed)  # type: ignore[attr-defined]
    feed.alerts = {}
    feed.last_msg = ""
    feed.last_score = 0
    for key, value in attrs.items():
        setattr(feed, key, value)

    def pub(topic: str, payload: object, retain: bool = False) -> None:
        sent.append((topic, payload, retain))

    feed.pub = pub  # type: ignore[method-assign]
    return feed, sent


def _frames(sent: list[tuple[str, object, bool]]) -> list[tuple[dict, bool]]:
    out: list[tuple[dict, bool]] = []
    for topic, payload, retain in sent:
        if topic != "ultron/risk/frame":
            continue
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert isinstance(payload, dict)
        out.append((payload, retain))
    return out


def test_frame_carries_the_whole_panel(mock_feed: object) -> None:
    feed, sent = _feed(
        mock_feed,
        alerts={"a1": {"ack": False}, "a2": {"ack": True}},
        last_msg="IP camera probed",
    )

    feed.frame(37)

    frames = _frames(sent)
    assert len(frames) == 1
    payload, retain = frames[0]
    assert payload == {
        "score": 37,
        "band": "YELLOW",
        "open": 1,
        "msg": "IP camera probed",
    }
    # Retained, so a board that is plugged in late, or a bridge that is
    # restarted, paints the current state instead of waiting for a change.
    assert retain is True


def test_risk_publishes_all_three_topics(mock_feed: object) -> None:
    feed, sent = _feed(mock_feed)

    feed.risk(62)

    topics = [topic for topic, _payload, _retain in sent]
    assert topics == ["ultron/risk/score", "ultron/risk/band", "ultron/risk/frame"]
    assert sent[0][1] == {"v": 62}
    assert sent[1][1] == {"b": mock_feed.band_for(62)}


def test_an_acknowledgement_drops_the_open_count(mock_feed: object) -> None:
    feed, sent = _feed(mock_feed, alerts={"a1": {"ack": False}}, last_msg="door opened")

    assert feed.open_alerts() == 1
    feed.frame(20)
    assert _frames(sent)[0][0]["open"] == 1

    feed.alerts["a1"] = {"ack": True}
    assert feed.open_alerts() == 0
    feed.frame(20)
    assert _frames(sent)[-1][0]["open"] == 0


def test_score_is_clamped_to_the_gauge(mock_feed: object) -> None:
    feed, sent = _feed(mock_feed)

    feed.frame(-30)
    feed.frame(400)

    assert _frames(sent)[0][0]["score"] == 0
    assert _frames(sent)[1][0]["score"] == 100


def test_a_long_message_is_truncated_not_dropped(mock_feed: object) -> None:
    feed, sent = _feed(mock_feed, last_msg="x" * 200)

    feed.frame(10)

    payload = _frames(sent)[0][0]
    assert len(payload["msg"]) == 60
    assert payload["msg"].startswith("xxx")


def test_band_can_be_passed_in_but_is_derived_when_absent(mock_feed: object) -> None:
    feed, sent = _feed(mock_feed)

    feed.frame(80, "PURPLE")
    feed.frame(80)

    assert _frames(sent)[0][0]["band"] == "PURPLE"
    assert _frames(sent)[1][0]["band"] == mock_feed.band_for(80)


def test_the_panel_beat_is_faster_than_the_link_timeout(mock_feed: object) -> None:
    """The whole point of LINK_TICK_S.

    The firmware declares LINK LOST after 3 s of silence. A feed that publishes
    only when the score moves leaves the panel blank through every plateau,
    while the console beside it shows a perfectly steady number.
    """
    assert mock_feed.LINK_TICK_S < 3.0


def test_last_score_is_remembered_for_a_repaint(mock_feed: object) -> None:
    """_on_ack repaints with the last known score, so it has to be kept."""
    feed, sent = _feed(mock_feed)

    feed.frame(44)
    assert feed.last_score == 44

    feed.frame(feed.last_score)
    assert _frames(sent)[-1][0]["score"] == 44
