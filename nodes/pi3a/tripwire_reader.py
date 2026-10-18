#!/usr/bin/env python3
"""ULTRON tripwire reader — Pi3a / Pi3b DETECTION side of the reed switch.

The ESP32-WROOM owns the reed switch itself: it debounces the contact and
reports *edges* as newline-delimited JSON, because a few millimetres of contact
bounce would otherwise read as a dozen separate tamper events. This service
turns those edges into MQTT.

The board is wired to the node's UART and never joins a network, so there is no
remote path that can silence it. That is the point: the case sensor is the one
detector an attacker standing in the room cannot switch off over the air.

Usage:
    python tripwire_reader.py --serial /dev/ttyUSB0 --node pi3a
    python tripwire_reader.py --node pi3a --replay        # no hardware
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from ultron import (  # noqa: E402
    TOPIC_HEALTH,
    TOPIC_TRIPWIRE,
    Link,
    add_mqtt_args,
    fail,
    setup_logging,
)

LOG = logging.getLogger("ultron.tripwire")

HEARTBEAT_TIMEOUT_S = 5.0   # the board blips at 1 Hz; silence is an alarm


def publish_edge(link: Link, node: str, event: dict) -> None:
    edge = str(event.get("edge") or "").lower()
    if edge not in ("open", "close"):
        LOG.warning("ignoring malformed edge %r", event)
        return
    payload = {
        "node": node,
        "edge": edge,
        "open": edge == "open",
        "opens": event.get("opens"),
        "ts": time.time(),
    }
    link.publish(f"{TOPIC_TRIPWIRE}/{node}", payload)
    LOG.info("case %s on %s (opens=%s)", edge, node, payload["opens"])


def run_serial(args: argparse.Namespace) -> int:
    try:
        import serial  # pyserial
    except ImportError:
        return fail("tripwire_reader needs pyserial:  pip install pyserial")

    link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                f"ultron-tripwire-{args.node}")
    LOG.info("reading %s for node %s", args.serial, args.node)

    last_beat = time.monotonic()
    try:
        with serial.Serial(args.serial, args.baud, timeout=1.0) as port:
            while True:
                raw = port.readline()
                now = time.monotonic()
                if not raw:
                    # Silence is not nothing. This is how the operator learns
                    # the sensor has been unplugged or the board killed.
                    if (now - last_beat) > HEARTBEAT_TIMEOUT_S:
                        last_beat = now
                        LOG.warning("no heartbeat from %s — sensor silent",
                                    args.node)
                        link.publish(f"{TOPIC_HEALTH}/tripwire-{args.node}",
                                     {"node": f"tripwire-{args.node}",
                                      "up": 0, "services": ["silent"]})
                    continue
                last_beat = now
                try:
                    event = json.loads(raw.decode("utf-8", "replace").strip())
                except ValueError:
                    LOG.warning("dropping unparseable frame: %r", raw[:80])
                    continue
                publish_edge(link, args.node, event)
    except KeyboardInterrupt:
        LOG.info("stopping tripwire reader")
    except OSError as exc:
        return fail(f"cannot open {args.serial}: {exc}")
    finally:
        link.stop()
    return 0


def run_replay(args: argparse.Namespace) -> int:
    """Exercise the MQTT path with no hardware attached."""
    link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                f"ultron-tripwire-{args.node}")
    LOG.info("replay mode: emitting an open/close pair on %s", args.node)
    try:
        publish_edge(link, args.node, {"edge": "open", "opens": 1})
        time.sleep(2)
        publish_edge(link, args.node, {"edge": "close", "opens": 1})
    finally:
        link.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ULTRON tripwire reader")
    ap.add_argument("--serial", default="/dev/ttyUSB0",
                    help="UART the ESP32-WROOM is wired to")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--node", default="pi3a", choices=["pi3a", "pi3b"])
    ap.add_argument("--replay", action="store_true",
                    help="emit one synthetic open/close pair and exit")
    add_mqtt_args(ap)
    args = ap.parse_args(argv)
    setup_logging(args.verbose)
    return run_replay(args) if args.replay else run_serial(args)


if __name__ == "__main__":
    sys.exit(main())
