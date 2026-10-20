#!/usr/bin/env python3
"""Turn a real port scan into a real verdict.

Watches the wire for TCP SYNs, counts how many distinct ports one source touches
inside a rolling window, and when that crosses the threshold publishes a RED
frame to the retained `ultron/risk/frame` topic. Everything subscribed to that
topic reacts -- the dashboard over its WebSocket and the ESP32 indicator over
MQTT -- so a scan on the LAN lights up both at the same moment, with no scripted
feed anywhere in the path.

This is deliberately small: it is a detector for the demo, not an IDS. It sees
SYNs that reach this host's interface, which is exactly what an nmap sweep of
this machine produces.

    sudo .venv/bin/python dashboard/tools/scan_watch.py
    # from another machine on the LAN:
    nmap -sT -p 1-500 <this machine's IP>

Needs root (or CAP_NET_RAW) because tcpdump needs it. Stop mock_feed.py first --
it republishes the retained frame about once a second and would overwrite us.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time

import paho.mqtt.client as mqtt

FRAME_TOPIC = "ultron/risk/frame"
# The dashboard's WebSocket bridge subscribes to these two scalars, not to the
# frame topic -- the frame is what the ESP32 renders. Publishing all three is
# what makes one sweep move both screens at once.
SCORE_TOPIC = "ultron/risk/score"
BAND_TOPIC = "ultron/risk/band"

# `10.0.0.5.51234 > 10.0.0.1.80: Flags [S], ...`  -- the dot before the port is
# the separator tcpdump uses, so the port is the trailing digits.
_ADDR = re.compile(r"(\d+\.\d+\.\d+\.\d+)\.(\d+) > (\d+\.\d+\.\d+\.\d+)\.(\d+):")


def sweep_ports(fields: re.Match[str]) -> tuple[str, int]:
    return fields.group(1), int(fields.group(4))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1", help="MQTT broker")
    ap.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    ap.add_argument("--iface", default="any", help="capture interface")
    ap.add_argument("--window", type=float, default=5.0,
                    help="seconds a source stays 'in flight'")
    ap.add_argument("--threshold", type=int, default=20,
                    help="distinct destination ports that make it a sweep")
    ap.add_argument("--score", type=int, default=72,
                    help="risk score to publish on a sweep (RED starts at 60)")
    ap.add_argument("--quiet", type=float, default=12.0,
                    help="seconds of calm before the verdict is cleared")
    args = ap.parse_args()

    if shutil.which("tcpdump") is None:
        print("scan_watch: tcpdump is not installed", file=sys.stderr)
        return 1

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:          # paho-mqtt 1.x, which has no version enum
        client = mqtt.Client()
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    def publish(score: int, band: str, open_n: int, msg: str) -> None:
        import json
        body = json.dumps({"score": score, "band": band, "open": open_n, "msg": msg})
        client.publish(FRAME_TOPIC, body, qos=1, retain=True)
        # The panel renders the frame; the dashboard renders the two scalars.
        # Both, retained, or only one of the screens moves.
        client.publish(SCORE_TOPIC, json.dumps({"v": score}), qos=1, retain=True)
        client.publish(BAND_TOPIC, json.dumps({"b": band}), qos=1, retain=True)
        # A score bump is not an event: the dashboard's log is driven by
        # ultron/alert/#, so without this the sweep changes colour and nothing
        # else. Only the alert is emitted; the recovery is silent, because a
        # cleared sweep is not something an operator needs in the log.
        if band == "RED":
            aid = f"scan-{int(time.time())}"
            alert = {"id": aid, "sev": "crit", "title": "Port sweep detected",
                     "src": "scan_watch/eth0", "body": msg,
                     "ts": int(time.time()), "ack": False}
            client.publish(f"ultron/alert/{aid}", json.dumps(alert), qos=1)
        print(f"[scan_watch] -> {body}", flush=True)

    # -l line-buffers, which matters when stdout is a pipe. A bare SYN is
    # `Flags [S]`; the replies are `[S.]` (SYN-ACK) and fall through below.
    proc = subprocess.Popen(
        ["tcpdump", "-i", args.iface, "-n", "-l",
         "tcp[tcpflags] & tcp-syn != 0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    ports: dict[str, dict[int, float]] = {}
    alerted: dict[str, float] = {}    # source -> when its last new port arrived
    print(f"[scan_watch] watching {args.iface}: {args.threshold} ports in "
          f"{args.window:g}s = RED", flush=True)

    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if "Flags [S]" not in line:
                continue
            match = _ADDR.search(line)
            if not match:
                continue
            src, dst_port = sweep_ports(match)
            now = time.monotonic()

            seen = ports.setdefault(src, {})
            seen[dst_port] = now
            for port, when in list(seen.items()):
                if now - when > args.window:
                    del seen[port]

            if len(seen) >= args.threshold:
                alerted[src] = now
                publish(args.score, "RED", len(seen),
                        f"nmap port sweep from {src} — {len(seen)} ports")
                # Start the count again so a long scan keeps refreshing the
                # alert instead of republishing on every packet.
                ports[src] = {}

            # If every alerting source has gone quiet, put the panel back.
            if alerted and all(now - t > args.quiet for t in alerted.values()):
                publish(8, "GREEN", 1, "port sweep ended — all clear")
                alerted.clear()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
