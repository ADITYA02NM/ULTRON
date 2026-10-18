#!/usr/bin/env python3
"""ULTRON dev-only scenario publisher.

DEV-ONLY. Never started by systemd. Publishes to the REAL broker so the whole
path (mosquitto -> server -> WebSocket -> browser) is exercised end to end.

It tells the SAME story as the in-browser simulation
(dashboard/web/src/lib/simulation.ts) so the two drivers never disagree. Keep
the beats, the endpoint roster and the wording of the two files in step.

    Phase A  every node and endpoint reports in, all healthy
    Phase B  ordinary household activity: the front door opens and closes, the
             kettle switches on, an unfamiliar phone joins the LAN and is then
             identified and trusted
    Phase C  the one genuine finding of the cycle: the camera is probed for
             default credentials (the attempt fails) plus a stale-firmware
             advisory. The score peaks YELLOW, the operator acknowledges the
             alert, and the score decays back to GREEN
    Phase D  close the cycle out, everything nominal, then start again

The peak is YELLOW. Most devices are healthy the whole time: this is a home
under watch, not a system falling apart.

There is a second script, `stress`, which narrates a real incident instead —
reconnaissance, a C2 beacon, a successful exploit, then lateral movement into
the governance node. It reaches RED and PURPLE, which `demo` structurally
cannot: demo's score tops out at 38, while RED needs 60 and PURPLE 85. Run it
to exercise the band chips, the ESP32 indicator and Pi3b's notification path.

This mock plays the role of BOTH the detection nodes AND the Pi4 risk engine (it
publishes ultron/risk/# too), and it also answers ultron/ack/# exactly the way
Pi3b does, so a laptop with no Pis sees the complete, working dashboard. On real
hardware Pi4's sentinel-risk owns risk/# and this tool is never run.

To watch the header go STALE/OFFLINE, stop the broker while this is running.

Usage:
    python mock_feed.py --host 127.0.0.1 --port 1883 [--user dev --pass dev]
    python mock_feed.py --script stress            # every detector, RED and PURPLE
    python mock_feed.py --script stress --cycles 1 # one pass, then exit
"""

from __future__ import annotations

import argparse
import json
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("mock_feed needs paho-mqtt:  pip install paho-mqtt", file=sys.stderr)
    raise SystemExit(1)

BANNER = r"""
============================================================
  ULTRON MOCK FEED  -  DEV-ONLY  -  DO NOT RUN IN PRODUCTION
  Publishes synthetic events to the live broker for demos.
============================================================
"""

# Keep in step with dashboard/web/src/lib/simulation.ts.
CYCLE_MS = 92000
HEALTH_TICK_S = 4.0
NODES = ("pi4", "pi3a", "pi3b", "esp32")


def band_for(score: int) -> str:
    if score >= 85:
        return "PURPLE"
    if score >= 60:
        return "RED"
    if score >= 30:
        return "YELLOW"
    return "GREEN"


def step_score(cur: int, target: int) -> int:
    """One 1 Hz tick of the risk engine approaching its target score.

    Mirrors scorePump() in lib/simulation.ts: move by max(2, ceil(diff/6)) so a
    big swing is brisk and a small one is calm.
    """
    diff = target - cur
    if diff == 0:
        return cur
    stride = min(abs(diff), max(2, -(-abs(diff) // 6)))
    return cur + (stride if diff > 0 else -stride)


# Smart-home endpoints on the monitored LAN (dev-only stand-ins). Each one is
# published on ultron/lan/<mac> so the IoT Topology panel paints it.
LAN_DEVICES = (
    {"mac": "B0:4E:26:1A:2B:3C", "ip": "192.168.100.61",
     "vendor": "Hikvision", "known": True, "label": "IP camera"},
    {"mac": "50:C7:BF:4D:5E:6F", "ip": "192.168.100.62",
     "vendor": "TP-Link", "known": True, "label": "Smart plug"},
    {"mac": "24:6F:28:7A:8B:9C", "ip": "192.168.100.63",
     "vendor": "Espressif", "known": True, "label": "Door sensor"},
)

# Two more endpoints the narration needs: a household device already on the
# LAN, and the phone that turns up mid-cycle.
LAN_HOUSE = {"mac": "00:11:22:33:44:55", "ip": "192.168.100.10", "vendor": "TP-Link"}
LAN_PHONE = {"mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.100.57", "vendor": "Apple"}


def lan_topic(mac: str) -> str:
    return "ultron/lan/" + mac.replace(":", "").lower()


class Feed:
    def __init__(self, host: str, port: int, user: str | None, password: str | None) -> None:
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ultron-mock")
        if user:
            self.client.username_pw_set(user, password or "")
        # Every alert we publish, so we can re-stamp it when it is acknowledged.
        self.alerts: dict[str, dict] = {}
        self.client.on_message = self._on_ack
        self.client.connect(host, port, keepalive=30)
        self.client.subscribe("ultron/ack/#", qos=1)
        self.client.loop_start()
        self._n = 0

    def pub(self, topic: str, payload: dict | str | int, retain: bool = False) -> None:
        data = payload if isinstance(payload, str) else json.dumps(payload)
        self.client.publish(topic, data, qos=1, retain=retain)
        print(f"  -> {topic:26s} {data}")

    def health(self, nodes: tuple[str, ...] = NODES) -> None:
        for node in nodes:
            self.pub(f"ultron/health/{node}",
                     {"node": node, "up": 3600 + self._n * 10,
                      "services": ["ok"]})
        self._n += 1

    def risk(self, score: int) -> None:
        score = max(0, min(100, score))
        self.pub("ultron/risk/score", {"v": score}, retain=True)
        self.pub("ultron/risk/band", {"b": band_for(score)}, retain=True)

    def lan(self, dev: dict) -> None:
        """Announce (or refresh) one endpoint on the monitored LAN."""
        now = int(time.time())
        self.pub(lan_topic(dev["mac"]),
                 {"mac": dev["mac"], "ip": dev["ip"], "vendor": dev["vendor"],
                  "known": dev.get("known", True),
                  "first_seen": now, "last_seen": now})

    def lan_all(self) -> None:
        for dev in LAN_DEVICES:
            self.lan(dev)

    def alert(self, aid: str, sev: str, title: str, src: str, body: str) -> None:
        payload = {"id": aid, "sev": sev, "title": title, "src": src,
                   "body": body, "ts": int(time.time()), "ack": False}
        self.alerts[aid] = payload
        self.pub(f"ultron/alert/{aid}", payload)

    def _on_ack(self, client, userdata, msg) -> None:  # noqa: ANN001 - paho callback
        """Pi3b's half of the demo: confirm an acknowledgement by re-stamping the
        alert. The dashboard ignores duplicate alert ids, but the store refreshes
        a row when the repeat carries ack=true — which is what makes the ACK
        button actually stick instead of quietly coming undone."""
        aid = msg.topic.rsplit("/", 1)[-1]
        payload = self.alerts.get(aid)
        if payload is None or payload.get("ack"):
            return
        stamped = dict(payload, ack=True, ack_ts=int(time.time()))
        self.alerts[aid] = stamped
        self.pub(f"ultron/alert/{aid}", stamped)

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


class Cycle:
    """Plays one full cycle of the watch against the broker.

    The score is pumped at 1 Hz toward a moving target and health is published
    every 4 s, exactly the way the browser simulation's pumps behave, so the
    gauge, the node tiles and the alert feed move identically whichever driver
    is running.
    """

    def __init__(self, feed: Feed, n: int, score: int = 0) -> None:
        self.feed = feed
        self.n = n
        self.seq = 0
        self.score = score
        self.target = 8
        self.t = 0.0
        self.tick = 0.0

    def _pump(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            slept = min(1.0, remaining)
            time.sleep(slept)
            self.t += slept
            self.tick += slept
            nxt = step_score(self.score, self.target)
            if nxt != self.score:
                self.score = nxt
                self.feed.risk(self.score)
            if self.tick >= HEALTH_TICK_S:
                self.tick = 0.0
                self.feed.health()

    def at(self, ms: int, fn) -> None:  # noqa: ANN001 - small local callback
        """Run `fn` when the cycle clock reaches `ms` milliseconds."""
        want = ms / 1000.0
        self._pump(max(0.0, want - self.t))
        self.t = want
        fn()

    def lan(self, dev: dict, known: bool = True) -> None:
        self.feed.lan({**dev, "known": known})

    def alert(self, sev: str, title: str, src: str, body: str) -> None:
        self.seq += 1
        self.feed.alert(f"c{self.n}-{self.seq}", sev, title, src, body)


def play_cycle(feed: Feed, n: int, score: int = 0) -> int:
    c = Cycle(feed, n, score)
    cam, plug, door = LAN_DEVICES

    # Yesterday's alerts are done with: forget them so a long-running demo does
    # not accumulate an unbounded registry (and so a stale ACK cannot re-stamp
    # an alert from a previous cycle).
    feed.alerts.clear()

    # Announce the roster before the story starts so the IoT Topology panel is
    # never empty while the first beats tick by.
    for dev in LAN_DEVICES:
        c.lan(dev)

    # -- Phase A: every node and endpoint reports in, all healthy -------------

    def a_pi4() -> None:
        c.lan(LAN_HOUSE)
        c.alert("info", "Pi4 governance online", "health/pi4",
                "192.168.100.1 — mosquitto, risk engine and dashboard up. Watchdog armed.")

    def a_camera() -> None:
        c.lan(cam)
        c.alert("info", f"{cam['label']} checked in", "detect/lan",
                f"{cam['vendor']} {cam['ip']} — 1080p stream healthy, RTSP 554 open, uptime 6 d.")

    def a_plug() -> None:
        c.lan(plug)
        c.alert("info", f"{plug['label']} reported in", "detect/lan",
                f"{plug['vendor']} {plug['ip']} — relay closed, drawing 11 W, Wi-Fi −54 dBm.")

    def a_door() -> None:
        c.lan(door)
        c.alert("info", f"{door['label']} paired", "detect/lan",
                f"{door['label']} {door['ip']} — front door contact, battery 92%, last event 3 h ago.")

    def a_node() -> None:
        c.alert("info", "Detection node online", "health/pi3a",
                "192.168.100.2 — Suricata 26,140 signatures loaded, LAN observer on eth0. No drops.")

    # -- Phase B: ordinary household activity, nothing wrong -----------------

    def b_open() -> None:
        c.alert("info", "Front door opened", "detect/lan",
                f"{door['label']} {door['ip']} — contact opened, resident arriving home.")

    def b_close() -> None:
        c.alert("info", "Front door closed", "detect/lan",
                f"{door['label']} {door['ip']} — contact closed after 5 s, battery unchanged at 92%.")

    def b_kettle() -> None:
        c.target = 14
        c.alert("info", f"{plug['label']} load changed", "detect/lan",
                f"{plug['label']} {plug['ip']} — draw 11 W → 46 W, kettle switched on.")

    def b_stream() -> None:
        c.alert("info", f"{cam['label']} stream healthy", "detect/lan",
                f"{cam['label']} {cam['ip']} — 1080p @ 15 fps, 0 dropped frames this hour.")

    def b_join() -> None:
        c.lan(LAN_PHONE, known=False)
        c.alert("info", "Unfamiliar device joined", "detect/lan",
                "AA:BB:CC:DD:EE:FF · 192.168.100.57 — first seen on the LAN, watching before trusting.")

    def b_identify() -> None:
        c.lan(LAN_PHONE, known=True)
        c.alert("info", "Unfamiliar device identified", "detect/lan",
                "AA:BB:CC:DD:EE:FF resolved to a household iPhone on the guest SSID — marked known.")

    # -- Phase C: the one genuine finding of the cycle -----------------------

    def c_probe() -> None:
        c.target = 38
        feed.pub("ultron/suricata/cam-default-creds",
                 {"signature": "ET SCAN default credential probe",
                  "severity": "yellow", "src": "suricata/eth0",
                  "src_ip": LAN_PHONE["ip"], "dest_ip": cam["ip"],
                  "sig_id": 2010935, "mac": cam["mac"]})
        c.alert("yellow", f"{cam['label']} probed for default credentials", "detect/suricata",
                f"192.168.100.57 → {cam['ip']} — 14 login attempts to the camera web UI in 30 s.")

    def c_rejected() -> None:
        c.alert("info", "Probe rejected", "detect/suricata",
                f"All 14 attempts failed — {cam['label']} is not on default credentials. No access gained.")

    def c_firmware() -> None:
        c.alert("yellow", f"{cam['label']} firmware is stale", "detect/lan",
                f"{cam['vendor']} {cam['ip']} — firmware v5.6.2, 14 months old, 3 known CVEs unpatched.")

    def c_ack() -> None:
        for aid, payload in list(feed.alerts.items()):
            if not payload.get("ack"):
                feed.pub(f"ultron/ack/{aid}", {"id": aid})

    def c_decay() -> None:
        c.target = 10

    # -- Phase D: close the cycle out, everything nominal --------------------

    def d_heartbeat() -> None:
        c.alert("info", "Pi3a heartbeat steady", "health/pi4",
                "Detection node reporting every 4 s, Suricata drop rate 0 %.")

    def d_refresh() -> None:
        feed.lan_all()
        c.lan(LAN_HOUSE)
        c.lan(LAN_PHONE)

    def d_indicator() -> None:
        c.alert("info", "Indicator reading GREEN", "health/esp32",
                "ESP32-C3 OLED GREEN, LED steady — no operator action required.")

    def d_nominal() -> None:
        c.alert("info", "All endpoints nominal", "health/pi4",
                "7/7 nodes healthy · 1 acknowledged advisory · 0 open critical. Watch continues.")

    def d_ack_rest() -> None:
        for aid, payload in list(feed.alerts.items()):
            if not payload.get("ack"):
                feed.pub(f"ultron/ack/{aid}", {"id": aid})

    beats = (
        (0, lambda: c.alert("info", "Watch started — narrating the home LAN", "risk/engine",
                            f"Cycle {n} beginning. Scoring from {c.score}.")),
        (1500, a_pi4),
        (3000, a_camera),
        (4500, a_plug),
        (7500, a_door),
        (9000, a_node),
        (12000, b_open),
        (17000, b_close),
        (19500, b_kettle),
        (22000, b_stream),
        (25000, b_join),
        (30000, b_identify),
        (34000, c_probe),
        (39000, c_rejected),
        (41000, c_firmware),
        (43000, c_ack),
        (45000, c_decay),
        (47000, d_heartbeat),
        (55000, d_refresh),
        (59000, d_indicator),
        (67000, d_nominal),
        (75000, d_ack_rest),
        (79000, d_refresh),
        (87000, lambda: c.alert("info", "Cycle complete — restarting watch", "risk/engine",
                                "Everything nominal. Beginning the next sweep.")),
    )

    for at_ms, fn in beats:
        c.at(at_ms, fn)

    # Run out the remainder of the cycle so the cadence stays steady.
    c.at(CYCLE_MS, lambda: None)
    return c.score


# The `stress` script's cycle clock, in ms. It is deliberately shorter than
# CYCLE_MS because it carries roughly three times the beats: the point is to
# exercise every detector in one pass.
STRESS_MS = 56000


def play_stress(feed: Feed, n: int, score: int = 0) -> int:
    """One dense drill: every event kind, all the way through RED and PURPLE.

    `play_cycle` is the honest story — a home under watch — and it peaks at
    YELLOW, so a laptop-only run can NEVER show a RED or PURPLE band (they need
    a score of 60 and 85; demo tops out at 38). That leaves the band chips, the
    gauge, the ESP32 indicator and Pi3b's notification path untested.

    This one narrates an actual incident — reconnaissance, a beacon, a
    successful exploit, then lateral movement into the governance node — and
    lets the score follow the story. Every alert kind the dashboard can render
    appears at least once, so a single pass covers the whole UI.
    """
    c = Cycle(feed, n, score)
    cam, plug, door = LAN_DEVICES

    feed.alerts.clear()
    for dev in LAN_DEVICES:
        c.lan(dev)

    # -- Phase A: the roster reports in --------------------------------------

    def a_pi4() -> None:
        c.lan(LAN_HOUSE)
        c.alert("info", "Pi4 governance online", "health/pi4",
                "192.168.100.1 — mosquitto, risk engine and dashboard up. Watchdog armed.")

    def a_camera() -> None:
        c.lan(cam)
        c.alert("info", f"{cam['label']} checked in", "detect/lan",
                f"{cam['vendor']} {cam['ip']} — 1080p stream healthy, RTSP 554 open, uptime 6 d.")

    def a_plug() -> None:
        c.lan(plug)
        c.alert("info", f"{plug['label']} reported in", "detect/lan",
                f"{plug['vendor']} {plug['ip']} — relay closed, drawing 11 W, Wi-Fi −54 dBm.")

    def a_door() -> None:
        c.lan(door)
        c.alert("info", f"{door['label']} paired", "detect/lan",
                f"{door['label']} {door['ip']} — front door contact, battery 92%, last event 3 h ago.")

    def a_node() -> None:
        c.alert("info", "Detection node online", "health/pi3a",
                "192.168.100.2 — Suricata 26,140 signatures loaded, LAN observer on eth0. No drops.")

    # -- Phase B: ordinary household activity --------------------------------

    def b_open() -> None:
        c.alert("info", "Front door opened", "detect/lan",
                f"{door['label']} {door['ip']} — contact opened, resident arriving home.")

    def b_close() -> None:
        c.alert("info", "Front door closed", "detect/lan",
                f"{door['label']} {door['ip']} — contact closed after 5 s, battery unchanged at 92%.")

    def b_kettle() -> None:
        c.target = 12
        c.alert("info", f"{plug['label']} load changed", "detect/lan",
                f"{plug['label']} {plug['ip']} — draw 11 W → 46 W, kettle switched on.")

    def b_join() -> None:
        c.lan(LAN_PHONE, known=False)
        c.alert("info", "Unfamiliar device joined", "detect/lan",
                "AA:BB:CC:DD:EE:FF · 192.168.100.57 — first seen on the LAN, watching before trusting.")

    def b_identify() -> None:
        c.lan(LAN_PHONE, known=True)
        c.alert("info", "Unfamiliar device identified", "detect/lan",
                "AA:BB:CC:DD:EE:FF resolved to a household iPhone on the guest SSID — marked known.")

    # -- Phase C: YELLOW — reconnaissance ------------------------------------

    def y_probe() -> None:
        c.target = 38
        feed.pub("ultron/suricata/cam-default-creds",
                 {"signature": "ET SCAN default credential probe",
                  "severity": "yellow", "src": "suricata/eth0",
                  "src_ip": LAN_PHONE["ip"], "dest_ip": cam["ip"],
                  "sig_id": 2010935, "mac": cam["mac"]})
        c.alert("yellow", f"{cam['label']} probed for default credentials", "detect/suricata",
                f"192.168.100.57 → {cam['ip']} — 14 login attempts to the camera web UI in 30 s.")

    def y_rejected() -> None:
        c.alert("info", "Probe rejected", "detect/suricata",
                f"All 14 attempts failed — {cam['label']} is not on default credentials. No access gained.")

    def y_firmware() -> None:
        c.target = 46
        c.alert("yellow", f"{cam['label']} firmware is stale", "detect/lan",
                f"{cam['vendor']} {cam['ip']} — firmware v5.6.2, 14 months old, 3 known CVEs unpatched.")
        c.alert("yellow", "Indicator reading YELLOW", "health/esp32",
                "ESP32-C3 OLED YELLOW — advisory only, no operator action required yet.")

    # -- Phase D: RED — it got in --------------------------------------------

    def r_beacon() -> None:
        c.target = 68
        feed.pub("ultron/suricata/cam-c2-beacon",
                 {"signature": "ET TROJAN Possible C2 Beacon (POST)",
                  "severity": "red", "src": "suricata/eth0",
                  "src_ip": cam["ip"], "dest_ip": "203.0.113.44",
                  "sig_id": 2027751, "mac": cam["mac"]})
        c.alert("red", f"{cam['label']} beaconing to an unknown host", "detect/suricata",
                f"{cam['ip']} → 203.0.113.44:8443 — 60 s jitter, 312 B POSTs, TLS certificate "
                "4 days old. Pattern matches command-and-control.")

    def r_unsigned() -> None:
        c.target = 76
        c.alert("red", f"{plug['label']} fetched unsigned firmware", "detect/lan",
                f"{plug['ip']} — 2.4 MB image pulled over plain HTTP from ota-cdn.lan with no "
                "signature. The device is now running code its vendor never published.")

    def r_cve() -> None:
        c.target = 82
        c.alert("red", f"{cam['label']} exploit attempt succeeded", "detect/suricata",
                "CVE-2021-36260 — 1 of 14 crafted requests returned HTTP 200 with a shell banner. "
                "Treating the camera as compromised.")
        c.alert("red", "Indicator reading RED", "health/esp32",
                "ESP32-C3 OLED RED, LED solid — operator attention required.")

    # -- Phase E: PURPLE — it spread -----------------------------------------

    def p_lateral() -> None:
        c.target = 88
        feed.pub("ultron/suricata/lateral-ssh",
                 {"signature": "ET SCAN SSH Brute Force from IoC Host",
                  "severity": "purple", "src": "suricata/eth0",
                  "src_ip": cam["ip"], "dest_ip": "192.168.100.2",
                  "sig_id": 2001219, "mac": cam["mac"]})
        c.alert("purple", "Lateral movement: camera → Pi4", "detect/suricata",
                f"{cam['ip']} → 192.168.100.2:22 — 240 authentication attempts in 40 s against the "
                "governance node. Dropped by the nftables set on the third retry.")

    def p_exfil() -> None:
        c.target = 94
        c.alert("purple", "Credential harvest attempt on Pi4", "detect/suricata",
                "The camera's session tried to write /etc/shadow and ~/.ssh/authorized_keys. "
                "Both denied — the API surface is read-only and the audit log is append-only.")

    def p_contain() -> None:
        c.target = 90
        c.alert("purple", "Containment: camera quarantined", "health/pi4",
                f"{cam['ip']} moved to the quarantine VLAN, DNS sinkholed, RTSP credentials "
                "revoked. Lateral path closed; the rest of the home is unaffected.")

    # -- Phase F: wind down ---------------------------------------------------

    def z_ack() -> None:
        for aid, payload in list(feed.alerts.items()):
            if not payload.get("ack"):
                feed.pub(f"ultron/ack/{aid}", {"id": aid})

    def z_decay() -> None:
        c.target = 10

    def z_heartbeat() -> None:
        c.alert("info", "Pi3a heartbeat steady", "health/pi4",
                "Detection node reporting every 4 s, Suricata drop rate 0 %.")

    def z_refresh() -> None:
        feed.lan_all()
        c.lan(LAN_HOUSE)
        c.lan(LAN_PHONE)

    def z_indicator() -> None:
        c.alert("info", "Indicator reading GREEN", "health/esp32",
                "ESP32-C3 OLED GREEN, LED steady — incident closed, no operator action required.")

    def z_nominal() -> None:
        c.alert("info", "All endpoints nominal", "health/pi4",
                "7/7 nodes healthy · 1 endpoint quarantined · 0 open critical. Watch continues.")

    beats = (
        (0, lambda: c.alert("info", "Watch started — incident drill", "risk/engine",
                            f"Stress cycle {n} beginning. Scoring from {c.score}. "
                            "Reconnaissance, compromise and lateral movement, all in one pass.")),
        (1000, a_pi4),
        (1800, a_camera),
        (2600, a_plug),
        (3400, a_door),
        (4200, a_node),
        (5000, b_open),
        (5800, b_close),
        (6600, b_kettle),
        (7000, b_join),
        (7500, b_identify),
        (8000, y_probe),
        (14000, y_rejected),
        (16000, y_firmware),
        (20000, r_beacon),
        (26000, r_unsigned),
        (30000, r_cve),
        (33000, p_lateral),
        (37000, p_exfil),
        (40000, p_contain),
        (43000, z_ack),
        (44500, z_decay),
        (46000, z_heartbeat),
        (47500, z_refresh),
        (49000, z_indicator),
        (51000, z_nominal),
        (52500, z_ack),
        (54000, z_refresh),
        (54500, lambda: c.alert("info", "Drill complete — restarting", "risk/engine",
                                "Incident closed and acknowledged. Beginning the next sweep.")),
    )

    for at_ms, fn in beats:
        c.at(at_ms, fn)

    c.at(STRESS_MS, lambda: None)
    return c.score


def run(feed: Feed, script: str = "demo", cycles: int = 0) -> None:
    if script == "stress":
        print("  STRESS script: every detector, all bands through PURPLE.")
    else:
        print("  beats mirror dashboard/web/src/lib/simulation.ts — keep them in step.")
    print("  to watch STALE/OFFLINE, stop the broker while this runs.")
    play = play_stress if script == "stress" else play_cycle
    n = 0
    score = 0
    while True:
        n += 1
        print(f"\n================ cycle {n} ================")
        score = play(feed, n, score)
        if cycles and n >= cycles:
            print(f"\nstopping after {n} cycle(s) — --cycles {cycles}.")
            break


def main() -> None:
    ap = argparse.ArgumentParser(description="ULTRON dev-only mock feed")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default=None)
    ap.add_argument("--pass", dest="password", default=None)
    ap.add_argument("--script", default="demo", choices=["demo", "stress"],
                    help="scenario to replay: demo mirrors the browser simulation and "
                         "peaks at YELLOW; stress exercises every detector and reaches "
                         "RED and PURPLE")
    ap.add_argument("--cycles", type=int, default=0,
                    help="stop after N cycles instead of looping forever (0 = forever)")
    args = ap.parse_args()

    print(BANNER)
    feed = Feed(args.host, args.port, args.user, args.password)
    try:
        run(feed, args.script, args.cycles)
    except KeyboardInterrupt:
        print("\nstopping mock feed.")
    finally:
        feed.stop()


if __name__ == "__main__":
    main()
