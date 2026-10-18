#!/usr/bin/env python3
"""ULTRON LAN watch — Pi3a DETECTION.

Watches the production LAN's neighbour table and reports endpoints the operator
has not blessed. A new MAC is not a verdict; it is a prompt to look. It scores
low on purpose (see LAN_SEVERITY_UNKNOWN in the risk engine) so a guest phone
cannot drag the house to RED on its own.

Vendor names come from a small built-in OUI table, never an online lookup. The
whole premise of this appliance is that it keeps working with the internet
unplugged, and a detection path that phones home is a detection path that can be
watched.

Usage:
    python lan_watch.py --interface eth0 --state /var/lib/ultron/lan.json
    python lan_watch.py --replay            # emit a synthetic join and exit
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from ultron import (  # noqa: E402
    Link,
    add_mqtt_args,
    lan_topic,
    setup_logging,
)

LOG = logging.getLogger("ultron.lan")

POLL_S = 15.0
MAX_SEEN = 2000

# A deliberately short table. It covers the vendors this appliance claims to
# monitor; unknown prefixes are reported as unknown rather than guessed at.
OUI_VENDORS = {
    "b0:4e:26": "Hikvision",
    "50:c7:bf": "TP-Link",
    "24:6f:28": "Espressif",
    "3c:61:05": "Espressif",
    "00:11:22": "Cimsys",
    "b8:27:eb": "Raspberry Pi Foundation",
    "dc:a6:32": "Raspberry Pi Trading",
    "e4:5f:01": "Raspberry Pi Trading",
    "44:07:0b": "Google",
    "f0:18:98": "Apple",
    "aa:bb:cc": "Locally administered",
}

MAC_RE = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")
NEIGH_RE = re.compile(r"^(?P<ip>\S+)\s+dev\s+(?P<dev>\S+)(?:\s+lladdr\s+(?P<mac>\S+))?", re.I)


def vendor_for(mac: str) -> str:
    return OUI_VENDORS.get(mac.lower()[:8], "unknown")


class Known:
    """First-seen ledger. Survives restarts so 'new' stays meaningful."""

    def __init__(self, path: str | None) -> None:
        self.path = Path(path) if path else None
        self.macs: dict[str, float] = {}
        if self.path and self.path.exists():
            try:
                self.macs = json.loads(self.path.read_text())
            except (ValueError, OSError):
                LOG.warning("could not read %s; starting fresh", self.path)

    def is_new(self, mac: str) -> bool:
        return mac.lower() not in self.macs

    def remember(self, mac: str) -> None:
        self.macs.setdefault(mac.lower(), time.time())
        if len(self.macs) > MAX_SEEN:
            oldest = sorted(self.macs.items(), key=lambda kv: kv[1])[: len(self.macs) // 4]
            for mac_, _ in oldest:
                self.macs.pop(mac_, None)

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.macs))


def neighbours(interface: str | None) -> list[tuple[str, str]]:
    """(mac, ip) pairs from the kernel's neighbour table."""
    try:
        out = subprocess.run(["ip", "-4", "neigh", "show"],
                             capture_output=True, text=True, timeout=5,
                             check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found: list[tuple[str, str]] = []
    for line in out.splitlines():
        m = NEIGH_RE.match(line.strip())
        if not m or not m.group("mac"):
            continue
        if interface and m.group("dev") != interface:
            continue
        found.append((m.group("mac"), m.group("ip")))
    return found


def publish(link: Link, known: Known, mac: str, ip: str, first_seen: float) -> None:
    new = known.is_new(mac)
    known.remember(mac)
    payload = {
        "mac": mac,
        "ip": ip,
        "vendor": vendor_for(mac),
        "known": not new,
        "first_seen": int(first_seen),
        "last_seen": int(time.time()),
    }
    link.publish(lan_topic(mac), payload)
    if new:
        LOG.warning("new endpoint %s %s (%s)", mac, ip, payload["vendor"])


def replay(link: Link) -> int:
    """Emit one unfamiliar endpoint so the pipeline can be exercised offline."""
    print("replay: publishing one unknown endpoint")
    link.publish(lan_topic("AA:BB:CC:DD:EE:FF"),
                 {"mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.100.57",
                  "vendor": vendor_for("AA:BB:CC:DD:EE:FF"), "known": False,
                  "first_seen": int(time.time()), "last_seen": int(time.time())})
    time.sleep(0.5)
    return 0


def run(args: argparse.Namespace) -> int:
    link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                "ultron-lan")
    known = Known(args.state)
    LOG.info("LAN watch up on %s (state %s)", args.interface or "any", args.state)
    try:
        while True:
            for mac, ip in neighbours(args.interface):
                first = known.macs.get(mac.lower(), time.time())
                publish(link, known, mac, ip, first)
            known.save()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        LOG.info("stopping LAN watch")
    finally:
        known.save()
        link.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ULTRON LAN watch (Pi3a detection)")
    ap.add_argument("--interface", default="eth0")
    ap.add_argument("--state", default="/var/lib/ultron/lan.json")
    ap.add_argument("--interval", type=float, default=POLL_S)
    ap.add_argument("--replay", action="store_true",
                    help="publish one synthetic endpoint and exit")
    add_mqtt_args(ap)
    args = ap.parse_args(argv)
    setup_logging(args.verbose)

    if args.replay:
        # Dispatch before touching the ledger: --replay exists precisely so the
        # pipeline can be exercised on a machine with no interface and no write
        # access to /var/lib, and the state path must not stand in the way.
        link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                    "ultron-lan")
        try:
            return replay(link)
        finally:
            link.stop()

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
