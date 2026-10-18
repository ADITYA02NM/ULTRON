#!/usr/bin/env python3
"""ULTRON Suricata tail — Pi3a DETECTION.

Follows Suricata's `eve.json` and republishes the alerts that matter on
`ultron/suricata/<signature id>`.

Only `event_type == "alert"` records are forwarded: eve.json also carries flow,
dns, tls and stats records, and forwarding those would drown the operator in
traffic that is not a finding.

The risk engine is deliberately NOT called from here. This process reports what
it saw; Pi4 decides what it means. A detector that scores its own findings can
be talked out of them.

Usage:
    python suricata_tail.py --eve /var/log/suricata/eve.json
    python suricata_tail.py --replay
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
    TOPIC_SURICATA,
    Link,
    add_mqtt_args,
    fail,
    setup_logging,
)

LOG = logging.getLogger("ultron.suricata")

# Suricata's own severity is 1 (most severe) to 3. Map it onto the band
# vocabulary so every source speaks one language downstream.
SEVERITY_MAP = {"1": "red", "2": "yellow", "3": "info"}
DEFAULT_SEVERITY = "yellow"


def severity_of(alert: dict) -> str:
    raw = str(alert.get("severity", "")).strip()
    if raw in SEVERITY_MAP:
        return SEVERITY_MAP[raw]
    # Suricata writes severity inside the alert object; some rule packs omit it.
    if alert.get("signature", "").upper().startswith(("ET EXPLOIT", "ET TROJAN")):
        return "red"
    return DEFAULT_SEVERITY


def envelope(record: dict) -> dict | None:
    """Map one eve.json record onto our contract, or None if it is not a finding."""
    if record.get("event_type") != "alert":
        return None

    alert = record.get("alert") or {}
    sig_id = alert.get("signature_id") or alert.get("gid")
    if sig_id is None:
        return None

    payload = {
        "sig_id": sig_id,
        "signature": alert.get("signature") or "Suricata alert",
        "category": alert.get("category"),
        "severity": severity_of(alert),
        "src": "suricata/eth0",
        "ts": record.get("timestamp") or time.time(),
    }
    for src_key, dest_key in (("src_ip", "src_ip"), ("dest_ip", "dest_ip")):
        value = record.get(src_key)
        if value:
            payload[dest_key] = value
    eth = record.get("ether") or {}
    if eth.get("src_mac"):
        payload["mac"] = eth["src_mac"]
    return payload


def run(args: argparse.Namespace) -> int:
    link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                "ultron-suricata")
    eve = Path(args.eve)
    if not eve.exists():
        return fail(f"{args.eve} not found (is Suricata running?)")

    LOG.info("tailing %s", eve)
    try:
        # Rotate-safe: on rotation the file shrinks; reopen rather than spin.
        with eve.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(0, 2)
            while True:
                line = fh.readline()
                if not line:
                    if fh.tell() > eve.stat().st_size:
                        LOG.info("eve.json rotated; reopening")
                        break
                    time.sleep(0.25)
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                payload = envelope(record)
                if payload is None:
                    continue
                topic = f"{TOPIC_SURICATA}/{payload['sig_id']}"
                link.publish(topic, payload)
                LOG.info("suricata %s: %s", payload["severity"],
                         payload["signature"])
    except KeyboardInterrupt:
        LOG.info("stopping suricata tail")
    finally:
        link.stop()
    return 0


def replay(args: argparse.Namespace) -> int:
    link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                "ultron-suricata")
    sample = {
        "event_type": "alert",
        "timestamp": time.time(),
        "src_ip": "192.168.100.57",
        "dest_ip": "192.168.100.61",
        "ether": {"src_mac": "AA:BB:CC:DD:EE:FF"},
        "alert": {"signature_id": 2010935,
                  "signature": "ET SCAN default credential probe",
                  "category": "Attempted Administrator Privilege Gain",
                  "severity": 2},
    }
    payload = envelope(sample)
    if payload is None:
        return fail("replay record did not map onto the contract")
    link.publish(f"{TOPIC_SURICATA}/{payload['sig_id']}", payload)
    LOG.info("replayed: %s", json.dumps(payload))
    link.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ULTRON Suricata eve.json tail")
    ap.add_argument("--eve", default="/var/log/suricata/eve.json")
    ap.add_argument("--replay", action="store_true")
    add_mqtt_args(ap)
    args = ap.parse_args(argv)
    setup_logging(args.verbose)
    return replay(args) if args.replay else run(args)


if __name__ == "__main__":
    sys.exit(main())
