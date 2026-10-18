#!/usr/bin/env python3
"""ULTRON WiFi monitor — Pi3a DETECTION (TL-WN722N).

Listens rather than speaks: the adapter is put into monitor mode and never
associates, so there is no management frame this appliance can be tricked into
answering.

What it is actually looking for is a rogue access point, and the sharpest case
is the evil twin — an AP broadcasting a name the house already trusts from a
radio the house does not own. That is scored RED, because it is the setup step
for an operator being served a convincing lie. A brand-new SSID is merely
YELLOW: neighbours add networks all the time.

Usage:
    python wifi_monitor.py --interface wlan1 --state /var/lib/ultron/wifi.json
    python wifi_monitor.py --replay       # emit a synthetic rogue AP and exit
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from ultron import (  # noqa: E402
    Link,
    add_mqtt_args,
    setup_logging,
)

LOG = logging.getLogger("ultron.wifi")

POLL_S = 20.0
TRUSTED_SSIDS = ("SENTINEL-SECURE",)


def topic_for(bssid: str) -> str:
    return "ultron/wifi/" + bssid.replace(":", "").lower()


class Baseline:
    """BSSIDs seen before. 'New' is only meaningful against a history."""

    def __init__(self, path: str | None) -> None:
        self.path = Path(path) if path else None
        self.bssids: dict[str, float] = {}
        if self.path and self.path.exists():
            try:
                self.bssids = json.loads(self.path.read_text())
            except (ValueError, OSError):
                LOG.warning("could not read %s; starting fresh", self.path)

    def is_new(self, bssid: str) -> bool:
        return bssid.lower() not in self.bssids

    def remember(self, bssid: str) -> None:
        self.bssids.setdefault(bssid.lower(), time.time())

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.bssids))


def visible(interface: str) -> list[dict]:
    """Access points currently audible on `interface`."""
    try:
        out = subprocess.run(["iw", "dev", interface, "scan"],
                             capture_output=True, text=True, timeout=10,
                             check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    aps: list[dict] = []
    current: dict | None = None
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("BSS "):
            current = {"bssid": stripped.split()[1], "ssid": "", "channel": None}
            aps.append(current)
        elif current is not None and stripped.startswith("SSID:"):
            current["ssid"] = stripped.split(":", 1)[1].strip()
        elif current is not None and stripped.startswith("DS Parameter set: channel"):
            try:
                current["channel"] = int(stripped.rsplit(" ", 1)[1])
            except (ValueError, IndexError):
                pass
    return aps


def severity_for(ssid: str, is_new: bool) -> str | None:
    """None means 'nothing worth saying'."""
    if ssid and ssid in TRUSTED_SSIDS:
        # A trusted name from an unseen radio is the evil-twin signature.
        return "red" if is_new else None
    if is_new:
        return "yellow"
    return None


def replay(link: Link) -> int:
    print("replay: publishing one rogue access point")
    link.publish(topic_for("AA:BB:CC:11:22:33"),
                 {"bssid": "AA:BB:CC:11:22:33", "ssid": "SENTINEL-SECURE",
                  "channel": 6, "severity": "red",
                  "title": "Evil twin: a second radio is using a trusted SSID",
                  "ts": int(time.time())})
    time.sleep(0.5)
    return 0


def run(args: argparse.Namespace) -> int:
    link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                "ultron-wifi")
    baseline = Baseline(args.state)
    if args.trusted:
        global TRUSTED_SSIDS
        TRUSTED_SSIDS = tuple(args.trusted)
    LOG.info("WiFi watch up on %s (trusted SSIDs: %s)",
             args.interface, ", ".join(TRUSTED_SSIDS) or "none")
    if not args.monitor and not _in_monitor_mode(args.interface):
        LOG.warning("%s does not look like it is in monitor mode; run "
                    "'airmon-ng start %s' first", args.interface, args.interface)

    try:
        while True:
            for ap in visible(args.interface):
                bssid = ap["bssid"]
                new = baseline.is_new(bssid)
                severity = severity_for(ap.get("ssid") or "", new)
                baseline.remember(bssid)
                if severity is None:
                    continue
                LOG.warning("%s %s %s (%s)", severity, ap.get("ssid") or "<hidden>",
                            bssid, ap.get("channel"))
                link.publish(topic_for(bssid), {
                    "bssid": bssid,
                    "ssid": ap.get("ssid") or "",
                    "channel": ap.get("channel"),
                    "severity": severity,
                    "title": ("Evil twin: a second radio is using a trusted SSID"
                              if severity == "red" else "Unfamiliar access point"),
                    "ts": int(time.time()),
                })
            baseline.save()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        LOG.info("stopping WiFi watch")
    finally:
        baseline.save()
        link.stop()
    return 0


def _in_monitor_mode(interface: str) -> bool:
    try:
        out = subprocess.run(["iw", "dev", interface, "info"],
                             capture_output=True, text=True, timeout=5,
                             check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "type monitor" in out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ULTRON WiFi monitor (Pi3a detection)")
    ap.add_argument("--interface", default="wlan1")
    ap.add_argument("--state", default="/var/lib/ultron/wifi.json")
    ap.add_argument("--interval", type=float, default=POLL_S)
    ap.add_argument("--trusted", action="append", default=[],
                    help="SSID the house trusts; repeatable")
    ap.add_argument("--monitor", action="store_true",
                    help="skip the monitor-mode sanity check")
    ap.add_argument("--replay", action="store_true",
                    help="publish one synthetic rogue AP and exit")
    add_mqtt_args(ap)
    args = ap.parse_args(argv)
    setup_logging(args.verbose)

    if args.replay:
        # As with lan_watch: never touch the baseline before replaying, so the
        # demo path works without an interface or write access to /var/lib.
        link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                    "ultron-wifi")
        try:
            return replay(link)
        finally:
            link.stop()

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
