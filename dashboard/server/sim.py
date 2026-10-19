"""Operator-driven sensor drill (Pi4 — GOVERNANCE).

The dashboard's SIMULATE control runs the real thing rather than a local puppet
show. This module owns at most one `dashboard/tools/mock_feed.py` child of the
server, so every beat it emits travels the same path a real sensor would:
MQTT -> bridge -> dashboard, MQTT -> Pi3b alert manager -> evidence vault and
notification. Nothing is injected into the UI locally, so what the operator
sees on screen is what actually went over the wire.

Trust boundary: only an authenticated WebSocket may ask for a drill (the socket
is validated at upgrade in main.py). The scenario name is checked against
SCRIPTS and the cycle count is clamped, so a client can never influence the
child's command line beyond those two closed sets. Nothing here ever publishes
to ultron/risk/# -- the feed does that, exactly as it does off the hardware.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

LOG = logging.getLogger("ultron.sim")

# Closed set. The value is forwarded to mock_feed.py as --script, never spliced
# into a shell string: start() uses create_subprocess_exec, not a shell.
SCRIPTS = ("demo", "stress")
DEFAULT_SCRIPT = "stress"
MAX_CYCLES = 50
STOP_GRACE_S = 5.0

_REPO = Path(__file__).resolve().parents[2]
_FEED = _REPO / "dashboard" / "tools" / "mock_feed.py"

OnChange = Callable[[dict[str, Any]], Awaitable[None]]


class Drill:
    """Owns at most one mock-feed child process at a time."""

    def __init__(self, host: str, port: int, feed: Path | None = None) -> None:
        self.host = host
        self.port = port
        # Injectable so the tests can drive the lifecycle without a broker.
        self.feed = feed or _FEED
        self._proc: asyncio.subprocess.Process | None = None
        self._script: str | None = None
        self._cycles: int = 0
        self._watcher: asyncio.Task[None] | None = None
        # Suspended, not ended. The child is stopped with SIGSTOP so it keeps
        # its cycle position and its timers: resuming continues the same story
        # rather than starting a new one.
        self._paused: bool = False
        self.on_change: OnChange | None = None

    # -- state ------------------------------------------------------------- #

    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    def status(self, **extra: Any) -> dict[str, Any]:
        live = self.running()
        return {
            "running": live,
            "paused": live and self._paused,
            "script": self._script if live else None,
            "cycles": self._cycles if live else 0,
            "pid": self._proc.pid if live and self._proc is not None else None,
            **extra,
        }

    async def _announce(self, **extra: Any) -> dict[str, Any]:
        payload = self.status(**extra)
        if self.on_change is not None:
            try:
                await self.on_change(payload)
            except Exception as exc:  # noqa: BLE001 - a dead socket must not stop a drill
                LOG.warning("drill announce failed: %s", exc)
        return payload

    # -- control ----------------------------------------------------------- #

    async def start(self, script: str = DEFAULT_SCRIPT, cycles: int = 0) -> dict[str, Any]:
        if script not in SCRIPTS:
            raise ValueError(f"unknown script: {script!r}")
        cycles = max(0, min(int(cycles), MAX_CYCLES))
        if self.running():
            if self._paused:
                # Pressing the button again on a suspended drill means "carry
                # on", not "throw this one away and start over".
                return await self.resume()
            return await self._announce(changed=False)
        if not self.feed.exists():
            raise FileNotFoundError(f"mock feed missing: {self.feed}")

        argv = [sys.executable, "-u", str(self.feed),
                "--host", self.host, "--port", str(self.port),
                "--script", script]
        if cycles:
            argv += ["--cycles", str(cycles)]

        self._script = script
        self._cycles = cycles
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        LOG.info("drill started script=%s cycles=%s pid=%s", script, cycles, self._proc.pid)
        self._watcher = asyncio.create_task(self._watch(self._proc))
        return await self._announce(changed=True)

    # -- pause ------------------------------------------------------------- #

    def _signal(self, sig: int) -> bool:
        """Best-effort signal to the child. False if there is nothing to signal."""
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return False
        try:
            os.kill(proc.pid, sig)
        except ProcessLookupError:
            return False
        return True

    async def pause(self) -> dict[str, Any]:
        """Suspend the drill where it stands, keeping its cycle position."""
        if not self.running() or self._paused:
            return await self._announce(changed=False)
        if not self._signal(signal.SIGSTOP):
            return await self._announce(changed=False)
        self._paused = True
        LOG.info("drill paused pid=%s", self._proc.pid if self._proc else "?")
        return await self._announce(changed=True)

    async def resume(self) -> dict[str, Any]:
        """Continue a suspended drill from exactly where it stopped."""
        if not self.running() or not self._paused:
            return await self._announce(changed=False)
        if not self._signal(signal.SIGCONT):
            return await self._announce(changed=False)
        self._paused = False
        LOG.info("drill resumed pid=%s", self._proc.pid if self._proc else "?")
        return await self._announce(changed=True)

    def _unpause_before_kill(self, proc: asyncio.subprocess.Process) -> None:
        """A stopped process cannot run its SIGTERM handler.

        Without this the grace period always expires and every paused drill is
        killed the hard way after STOP_GRACE_S.
        """
        if not self._paused:
            return
        self._paused = False
        try:
            os.kill(proc.pid, signal.SIGCONT)
        except ProcessLookupError:
            pass

    async def _cancel_watcher(self) -> None:
        """Retire the watcher so only one coroutine reports a given ending."""
        watcher = self._watcher
        self._watcher = None
        if watcher is None or watcher.done():
            return
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass

    async def stop(self) -> dict[str, Any]:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            self._proc = None
            self._script = None
            self._cycles = 0
            return await self._announce(changed=False)

        # The watcher is awaiting the same proc.wait(). If it wins the race it
        # announces "stopped" as well, and every operator gets the frame twice.
        await self._cancel_watcher()
        self._unpause_before_kill(proc)
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=STOP_GRACE_S)
        except asyncio.TimeoutError:
            LOG.warning("drill pid=%s ignored SIGTERM; killing", proc.pid)
            proc.kill()
            await proc.wait()
        LOG.info("drill stopped pid=%s", proc.pid)
        if self._proc is proc:
            self._proc = None
            self._script = None
            self._cycles = 0
            self._paused = False
        return await self._announce(changed=True)

    async def _watch(self, proc: asyncio.subprocess.Process) -> None:
        """Report a drill that ended on its own (--cycles, or a crash)."""
        await proc.wait()
        if self._proc is not proc:
            return  # superseded by stop()
        self._proc = None
        self._script = None
        self._cycles = 0
        self._paused = False
        if proc.returncode == 0:
            LOG.info("drill finished on its own (rc=0)")
            await self._announce(changed=True, finished=True)
        else:
            LOG.warning("drill died rc=%s", proc.returncode)
            await self._announce(changed=True, failed=True, rc=proc.returncode)

    async def aclose(self) -> None:
        """Server shutdown: never leave an orphan publishing to the broker."""
        await self._cancel_watcher()
        proc = self._proc
        self._proc = None
        if proc is None or proc.returncode is not None:
            return
        self._unpause_before_kill(proc)
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=STOP_GRACE_S)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
