#!/usr/bin/env python3
"""Turn a real port scan into a real verdict.

Watches the wire for TCP SYNs, counts how many distinct ports one source touches
inside a rolling window, and when that crosses the threshold publishes a RED
frame. Three topics go out together because each screen reads a different one:

    ultron/risk/score   the dashboard's number
    ultron/risk/band    the dashboard's chip and the panel's trace colour
    ultron/risk/frame   the ESP32's full frame, message line included
    ultron/alert/<id>   the dashboard's event log

so one sweep moves the browser, the OLED and the NeoPixel at the same moment,
with no scripted feed anywhere in the path.

Point it at a camera and the camera is what gets named and dropped onto the
topology map -- the scanned host is the victim, not the scanner:

    sudo .venv/bin/python dashboard/tools/scan_watch.py \\
        --camera-ip 10.0.0.42 --camera-name "IP camera"

    nmap -sT -p 1-500 10.0.0.42

Without --camera-ip the alert still fires, naming both ends of the sweep.

This is deliberately small: it is a detector for the demo, not an IDS. It sees
SYNs that reach this host's interface, which is exactly what an nmap sweep
produces. It needs CAP_NET_RAW (or root) because tcpdump does.

Stop mock_feed.py first -- it republishes the retained frame about once a
second and would overwrite us.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import threading
import time

import paho.mqtt.client as mqtt

FRAME_TOPIC = "ultron/risk/frame"
# The dashboard's WebSocket bridge subscribes to these two scalars, not to the
# frame topic -- the frame is what the ESP32 renders. Publishing all three is
# what makes one sweep move both screens at once.
SCORE_TOPIC = "ultron/risk/score"
BAND_TOPIC = "ultron/risk/band"
LAN_TOPIC = "ultron/lan/scan-watch"

# `10.0.0.5.51234 > 10.0.0.42.80: Flags [S], ...` -- the dot before the port is
# the separator tcpdump uses, so the port is the trailing digits.
_ADDR = re.compile(r"(\d+\.\d+\.\d+\.\d+)\.(\d+) > (\d+\.\d+\.\d+\.\d+)\.(\d+):")

# With `-e` tcpdump puts the link-layer address immediately before `ethertype`.
# On loopback it is all zeroes, which is why an empty MAC is treated as "not on
# a real segment" rather than as a device.
_MAC = re.compile(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\s+ethertype")

# A stable signature id, because the dashboard keys the IDS feed by it. It is
# the kind of id an ET rule would carry, and it is ours to name.
SID_PORT_SWEEP = 2010935


def sweep_ports(fields: re.Match[str]) -> tuple[str, str, int]:
    """(source, destination, destination port) from a tcpdump SYN line."""
    return fields.group(1), fields.group(3), int(fields.group(4))


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
    ap.add_argument("--quiet", type=float, default=10.0,
                    help="seconds of calm before the verdict returns to GREEN")
    ap.add_argument("--ack-after", type=float, default=10.0,
                    help="seconds after a sweep before its alert is acknowledged")
    ap.add_argument("--cooldown", type=float, default=6.0,
                    help="seconds before one source may raise an alert again")
    ap.add_argument("--camera-ip", default="",
                    help="treat a sweep of this address as an IP camera probe")
    ap.add_argument("--camera-name", default="IP camera",
                    help="label used for the camera in alerts and on the map")
    ap.add_argument("--camera-mac", default="02:00:00:00:00:01",
                    help="locally administered placeholder so the camera can be "
                         "placed on the topology map (no ARP lookup is done)")
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

    started = time.time()
    esp_seen: dict[str, float] = {}

    def mqtt_peers() -> list[str]:
        """Remote clients holding an MQTT session on this broker.

        The indicator is the only off-host subscriber in this rig, so a peer
        that is not loopback is the board saying it is alive. That is an
        observation rather than an assumption -- the board publishes nothing.
        """
        try:
            out = subprocess.run(
                ["ss", "-tnH", "state", "established", "( sport = :1883 )"],
                capture_output=True, text=True, timeout=2,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        peers: list[str] = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            peer = parts[-1].rsplit(":", 1)[0]
            if peer and not peer.startswith("127.") and peer not in peers:
                peers.append(peer)
        return peers

    def announce_self() -> None:
        """Put this host on the topology map.

        Without it the graph opens on "Awaiting ARP" even though the appliance
        is plainly on the wire -- an empty map reads as a broken sensor.
        """
        try:
            out = subprocess.run(["ip", "-4", "route", "get", "1.1.1.1"],
                                 capture_output=True, text=True, timeout=2).stdout
            words = out.split()
            ip = words[words.index("src") + 1] if "src" in words else ""
            dev = words[words.index("dev") + 1] if "dev" in words else ""
            mac = ""
            if dev:
                with open(f"/sys/class/net/{dev}/address", encoding="utf-8") as fh:
                    mac = fh.read().strip()
        except (OSError, ValueError, subprocess.SubprocessError):
            return
        if not ip or not mac:
            return
        stamp = int(time.time())
        client.publish(LAN_TOPIC, json.dumps({"mac": mac, "ip": ip,
                                              "vendor": "ultron-appliance",
                                              "known": True,
                                              "first_seen": stamp,
                                              "last_seen": stamp}),
                       qos=1, retain=True)

    def health_loop() -> None:
        """Keep the hardware panel honest about the roles this rig plays.

        On the laptop this sensor stands in for two nodes: it emits the
        Suricata-shaped detection event (Pi3a) and it publishes the verdict
        (Pi4). Both are real work happening right here, so a heartbeat for
        each is a statement of fact rather than decoration.
        """
        announce_self()
        while True:
            up = int(time.time() - started) + 1
            for node in ("pi4", "pi3a"):
                client.publish(f"ultron/health/{node}",
                               json.dumps({"node": node, "up": up,
                                           "services": ["ok"]}),
                               qos=0, retain=True)
            for peer in mqtt_peers():
                first = esp_seen.setdefault(peer, time.time())
                client.publish("ultron/health/esp32",
                               json.dumps({"node": "esp32",
                                           "up": int(time.time() - first) + 1,
                                           "services": ["mqtt"]}),
                               qos=0, retain=True)
            time.sleep(5)

    threading.Thread(target=health_loop, daemon=True, name="health").start()

    def publish(score: int, band: str, open_n: int, msg: str,
                title: str = "Port sweep detected",
                **extra: object) -> str | None:
        # The alert goes first. The alerts node mails a band change together
        # with the alert that raised it, and it reads that alert back out of the
        # vault -- so it has to be there before the band message lands.
        alert_id: str | None = None
        if band == "RED":
            stamp = int(time.time())
            alert_id = f"scan-{stamp}"
            alert = {"id": alert_id, "sev": "crit", "title": title,
                     "src": "scan_watch", "body": msg,
                     "ts": stamp, "ack": False, **extra}
            client.publish(f"ultron/alert/{alert_id}", json.dumps(alert),
                           qos=1)
        body = json.dumps({"score": score, "band": band, "open": open_n, "msg": msg})
        client.publish(FRAME_TOPIC, body, qos=1, retain=True)
        # The panel renders the frame; the dashboard renders the two scalars.
        # Both, retained, or only one of the screens moves.
        client.publish(SCORE_TOPIC, json.dumps({"v": score}), qos=1, retain=True)
        client.publish(BAND_TOPIC, json.dumps({"b": band}), qos=1, retain=True)
        print(f"[scan_watch] -> {body}", flush=True)
        return alert_id

    # -l line-buffers, which matters when stdout is a pipe. A bare SYN is
    # `Flags [S]`; the replies are `[S.]` (SYN-ACK) and fall through below.
    proc = subprocess.Popen(
        ["tcpdump", "-i", args.iface, "-n", "-l", "-e",
         "tcp[tcpflags] & tcp-syn != 0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    ports: dict[str, dict[int, float]] = {}
    targets: dict[str, str] = {}      # source -> most recent destination
    last_pub: dict[str, float] = {}   # source -> when it last raised an alert
    last_port: dict[str, float] = {}  # source -> when it last touched a port
    macs: dict[str, str] = {}         # source -> link-layer address, when known
    alerted: set[str] = set()
    alert_ids: dict[str, str] = {}    # source -> the alert it raised
    raised_at: dict[str, float] = {}  # source -> when that alert went out

    def on_ack(_c, _u, msg) -> None:  # noqa: ANN001 - paho callback signature
        """The operator acknowledged the sweep, so the console calms down now.

        The ten-second timer closes the row on its own, but a human pressing
        ACK is a stronger statement than a timer: the incident is dealt with,
        so the verdict goes back to calm immediately rather than waiting out
        the quiet window.
        """
        aid = msg.topic.rsplit("/", 1)[-1]
        for source, known in list(alert_ids.items()):
            if known != aid:
                continue
            alert_ids.pop(source, None)
            raised_at.pop(source, None)
            alerted.discard(source)
            last_port.pop(source, None)
            print(f"[scan_watch] {aid} acknowledged by the operator", flush=True)
            if not alerted:
                publish(8, "GREEN", 1, "alert acknowledged — all clear")
            return

    client.on_message = on_ack
    client.subscribe("ultron/ack/#", qos=1)
    print(f"[scan_watch] watching {args.iface}: {args.threshold} ports in "
          f"{args.window:g}s = RED", flush=True)
    if args.camera_ip:
        print(f"[scan_watch] {args.camera_name} is {args.camera_ip} "
              f"({args.camera_mac})", flush=True)

    # Recovery has to run on a clock, not on traffic. tcpdump's pipe goes quiet
    # the moment a scan ends, so a check inside the read loop would never run
    # again -- which is exactly how a finished sweep stayed RED forever.
    stop = threading.Event()

    def watchdog() -> None:
        while not stop.wait(1.0):
            now = time.monotonic()
            # Acknowledge on a clock, not on calm traffic. An operator wants the
            # row closed a known number of seconds after the sweep, whether or
            # not the scanner is still probing -- waiting for silence means a
            # slow scan leaves a critical row open for minutes.
            for source, aid in list(alert_ids.items()):
                if now - raised_at.get(source, now) >= args.ack_after:
                    client.publish(f"ultron/ack/{aid}",
                                   json.dumps({"ack": True}), qos=1)
                    print(f"[scan_watch] acked {aid} "
                          f"{args.ack_after:g}s after the sweep", flush=True)
                    alert_ids.pop(source, None)
                    raised_at.pop(source, None)
            if alerted and all(now - last_port.get(s, 0.0) > args.quiet
                               for s in list(alerted)):
                publish(8, "GREEN", 1, "port sweep ended — all clear")
                alerted.clear()

    threading.Thread(target=watchdog, daemon=True).start()

    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if "Flags [S]" not in line:
                continue
            match = _ADDR.search(line)
            if not match:
                continue
            src, dst, dst_port = sweep_ports(match)
            now = time.monotonic()
            targets[src] = dst
            link = _MAC.search(line)
            if link and link.group(1) != "00:00:00:00:00:00":
                macs[src] = link.group(1)

            seen = ports.setdefault(src, {})
            seen[dst_port] = now
            for port, when in list(seen.items()):
                if now - when > args.window:
                    del seen[port]

            # Only sweep-shaped traffic refreshes the recovery clock. A browser
            # opening its own connections emits SYNs from this host too, and
            # counting those kept the verdict RED long after the scan finished.
            if len(seen) >= args.threshold:
                last_port[src] = now

            # One alert per cooldown. Without this a fast 500-port sweep
            # republishes on every twenty ports -- twenty-five alerts for one
            # scan, which is noise, not a verdict.
            if (len(seen) >= args.threshold
                    and now - last_pub.get(src, -1e9) >= args.cooldown):
                last_pub[src] = now
                alerted.add(src)
                stamp = int(time.time())
                mac = macs.get(src, "")
                count = len(seen)

                # The detect lane is fed by ultron/suricata/#, so a sweep has to
                # be a signature hit before it is a verdict. Without this the
                # pipeline shows a gap exactly where the detection happened.
                sig: dict[str, object] = {
                    "sig_id": SID_PORT_SWEEP,
                    "signature": f"ET SCAN nmap port sweep ({count} ports)",
                    "severity": "crit",
                    "src_ip": src, "dest_ip": dst, "ports": count,
                }
                if mac:
                    sig["mac"] = mac
                client.publish(f"ultron/suricata/{SID_PORT_SWEEP}",
                               json.dumps(sig), qos=1)

                if args.camera_ip and dst == args.camera_ip:
                    # The scanned host is what gets flagged, so name it -- and
                    # put it on the topology map, because an alert an operator
                    # cannot find on the map is only half an alert.
                    title = f"{args.camera_name} probed"
                    msg = (f"{args.camera_name} {dst} probed — {count} ports "
                           f"from {src}")
                    lan = {"mac": args.camera_mac, "ip": dst,
                           "vendor": args.camera_name, "known": False,
                           "first_seen": stamp, "last_seen": stamp}
                    client.publish(LAN_TOPIC, json.dumps(lan), qos=1, retain=True)
                elif mac:
                    # The scanner is a device on the wire before it is a verdict.
                    # The gateway hands us its real MAC, so it belongs on the map
                    # instead of appearing as an anonymous score bump.
                    lan = {"mac": mac, "ip": src, "vendor": "scanner",
                           "known": False, "first_seen": stamp,
                           "last_seen": stamp}
                    client.publish(LAN_TOPIC, json.dumps(lan), qos=1, retain=True)
                    title = "Port sweep detected"
                    msg = f"{src} ({mac}) swept {count} ports on {dst}"
                else:
                    title = "Port sweep detected"
                    msg = (f"nmap port sweep from {src} against {dst} — "
                           f"{count} ports")
                raised = publish(args.score, "RED", count, msg, title,
                                 src_ip=src, dest_ip=dst, ports=count)
                if raised:
                    alert_ids[src] = raised
                    raised_at[src] = time.monotonic()


    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        proc.terminate()
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
