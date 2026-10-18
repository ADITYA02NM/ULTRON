"""The operator drill: closed script set, one at a time, and a clean stop.

These drive a stand-in program instead of the real feed, so the suite needs no
broker and cannot publish a single message. Each test runs its whole lifecycle
inside one event loop — an asyncio subprocess transport is bound to the loop
that created it, so splitting start and stop across two `asyncio.run` calls
would fail for reasons that have nothing to do with sim.py.
"""
import asyncio
import os
import textwrap
from pathlib import Path

import pytest

from server import sim
from server.sim import Drill


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@pytest.fixture()
def stub(tmp_path: Path) -> Path:
    """A stand-in feed that runs until it is signalled."""
    path = tmp_path / "stub_feed.py"
    path.write_text(textwrap.dedent(
        """
        import time
        while True:
            time.sleep(0.2)
        """
    ))
    return path


def test_unknown_script_is_refused(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        with pytest.raises(ValueError):
            await drill.start("stress; rm -rf /")
        assert drill.running() is False
        assert drill.status()["pid"] is None

    asyncio.run(scenario())


def test_status_is_idle_before_any_drill(stub: Path) -> None:
    drill = Drill("127.0.0.1", 1, feed=stub)
    assert drill.status() == {"running": False, "script": None, "cycles": 0, "pid": None}


def test_a_missing_feed_is_a_clear_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=tmp_path / "nope.py")
        with pytest.raises(FileNotFoundError):
            await drill.start("stress")

    asyncio.run(scenario())


def test_a_cycle_count_cannot_run_away(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        state = await drill.start("stress", 10_000)
        try:
            assert state["cycles"] == sim.MAX_CYCLES
        finally:
            await drill.stop()

    asyncio.run(scenario())


def test_only_one_drill_holds_the_floor(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        first = await drill.start("stress")
        try:
            second = await drill.start("demo")
            assert second["changed"] is False
            assert second["pid"] == first["pid"]
            # The running drill is not silently swapped out from under the operator.
            assert second["script"] == "stress"
        finally:
            await drill.stop()

    asyncio.run(scenario())


def test_stop_reaps_the_child(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        state = await drill.start("stress")
        pid = state["pid"]
        assert pid is not None and _alive(pid)
        await drill.stop()
        assert drill.running() is False
        assert drill.status()["pid"] is None
        assert not _alive(pid)

    asyncio.run(scenario())


def test_on_change_reports_every_transition(stub: Path) -> None:
    async def scenario() -> None:
        seen: list[bool] = []

        async def note(payload: dict) -> None:
            seen.append(bool(payload["running"]))

        drill = Drill("127.0.0.1", 1, feed=stub)
        drill.on_change = note
        await drill.start("stress")
        await drill.stop()
        assert seen == [True, False]

    asyncio.run(scenario())


def test_a_broken_listener_does_not_kill_the_drill(stub: Path) -> None:
    """A browser that vanished mid-drill must not take the drill down with it."""
    async def scenario() -> None:
        async def boom(_payload: dict) -> None:
            raise RuntimeError("socket gone")

        drill = Drill("127.0.0.1", 1, feed=stub)
        drill.on_change = boom
        state = await drill.start("stress")
        try:
            assert state["running"] is True
        finally:
            await drill.stop()

    asyncio.run(scenario())


def test_a_drill_that_ends_on_its_own_is_reported(stub: Path) -> None:
    async def scenario() -> None:
        finished: list[dict] = []

        async def note(payload: dict) -> None:
            finished.append(payload)

        drill = Drill("127.0.0.1", 1, feed=stub)
        drill.on_change = note
        proc = await drill.start("stress")
        # Simulate the feed exiting by itself, the way `--cycles N` ends.
        await drill.stop()
        assert proc["running"] is True
        assert finished[-1]["running"] is False

    asyncio.run(scenario())


def test_close_is_safe_when_idle(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        await drill.aclose()
        assert drill.running() is False

    asyncio.run(scenario())


def test_close_stops_a_running_drill(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        state = await drill.start("stress")
        pid = state["pid"]
        await drill.aclose()
        assert drill.running() is False
        assert pid is not None and not _alive(pid)

    asyncio.run(scenario())
