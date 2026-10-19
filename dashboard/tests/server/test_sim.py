"""The operator drill: closed script set, one at a time, pausable, cleanly stopped.

These drive a stand-in program instead of the real feed, so the suite needs no
broker and cannot publish a single message. Each test runs its whole lifecycle
inside one event loop — an asyncio subprocess transport is bound to the loop
that created it, so splitting start and stop across two `asyncio.run` calls
would fail for reasons that have nothing to do with sim.py.
"""
import asyncio
import os
import textwrap
import time
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


def _state(pid: int) -> str:
    """Linux process state. 'T' means the kernel has it stopped, not gone."""
    return Path(f"/proc/{pid}/stat").read_text().split()[2]


def _wait_state(pid: int, want: str, timeout: float = 3.0) -> str:
    deadline = time.monotonic() + timeout
    state = _state(pid)
    while state != want and time.monotonic() < deadline:
        time.sleep(0.02)
        state = _state(pid)
    return state


def _wait_running(pid: int, timeout: float = 3.0) -> str:
    """Wait for a stopped child to become schedulable again."""
    deadline = time.monotonic() + timeout
    state = _state(pid)
    while state == "T" and time.monotonic() < deadline:
        time.sleep(0.02)
        state = _state(pid)
    return state


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
    assert drill.status() == {
        "running": False, "paused": False, "script": None, "cycles": 0, "pid": None,
    }


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


# ── pause: suspended where it stands, not ended ──────────────────────────────
#
# The drill is a real child process, so pausing is SIGSTOP: the cycle keeps its
# position and its timers, and resuming continues the same story instead of
# replaying the first two minutes.


def test_pause_suspends_the_child_without_ending_it(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        state = await drill.start("stress")
        pid = state["pid"]
        paused = await drill.pause()
        try:
            assert paused["paused"] is True
            assert paused["running"] is True          # still the same drill
            assert paused["pid"] == pid
            assert drill.running() is True
            assert _wait_state(pid, "T") == "T"       # the kernel really stopped it
            assert _alive(pid)                        # and did not kill it
        finally:
            await drill.stop()

    asyncio.run(scenario())


def test_resume_continues_the_same_process(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        started = await drill.start("stress")
        await drill.pause()
        resumed = await drill.resume()
        try:
            assert resumed["paused"] is False
            assert resumed["pid"] == started["pid"]   # same cycle, not a new one
            assert _wait_running(started["pid"]) != "T"
        finally:
            await drill.stop()

    asyncio.run(scenario())


def test_start_on_a_paused_drill_resumes_it(stub: Path) -> None:
    """Pressing the button again means carry on, not throw this one away."""
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        started = await drill.start("stress")
        await drill.pause()
        again = await drill.start("demo")
        try:
            assert again["changed"] is True
            assert again["paused"] is False
            assert again["pid"] == started["pid"]
            assert again["script"] == "stress"
        finally:
            await drill.stop()

    asyncio.run(scenario())


def test_stop_still_reaps_a_paused_child(stub: Path) -> None:
    """A stopped process never runs its SIGTERM handler.

    Without a SIGCONT first, stop() would always burn the whole grace period and
    then kill the drill the hard way.
    """
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        state = await drill.start("stress")
        pid = state["pid"]
        await drill.pause()
        await drill.stop()
        assert drill.running() is False
        assert drill.status()["pid"] is None
        assert not _alive(pid)

    asyncio.run(scenario())


def test_pause_and_resume_are_idempotent(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        await drill.start("stress")
        try:
            assert (await drill.pause())["changed"] is True
            second = await drill.pause()
            assert second["changed"] is False
            assert second["paused"] is True
            assert (await drill.resume())["changed"] is True
            assert (await drill.resume())["changed"] is False
        finally:
            await drill.stop()

    asyncio.run(scenario())


def test_pause_when_idle_is_a_noop(stub: Path) -> None:
    async def scenario() -> None:
        drill = Drill("127.0.0.1", 1, feed=stub)
        state = await drill.pause()
        assert state["changed"] is False
        assert state["running"] is False
        assert state["paused"] is False
        assert (await drill.resume())["changed"] is False

    asyncio.run(scenario())


def test_on_change_reports_pause_and_resume(stub: Path) -> None:
    async def scenario() -> None:
        seen: list[bool] = []

        async def note(payload: dict) -> None:
            seen.append(bool(payload["paused"]))

        drill = Drill("127.0.0.1", 1, feed=stub)
        drill.on_change = note
        await drill.start("stress")
        await drill.pause()
        await drill.resume()
        await drill.stop()
        assert seen == [False, True, False, False]

    asyncio.run(scenario())
