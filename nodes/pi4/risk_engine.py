#!/usr/bin/env python3
"""ULTRON risk engine — Pi4 GOVERNANCE.

Fuses the detection sources into one 0-100 score and one band, then publishes
both to MQTT for the dashboard and writes a compact line to the ESP32-C3 over
USB serial for the shelf indicator.

The score is a weighted sum of *decaying* per-source severities:

    score = 100 * Σ (weight_i · severity_i · ½^(age_i / HALF_LIFE))

Weights are the documented ones: Suricata .40, tripwire .30, WiFi .20, LAN .10.
Severities decay on a half-life rather than snapping to zero, because an
intrusion that happened four minutes ago is less urgent than one happening now,
but it is not nothing — and a score that resets instantly teaches an operator
to stop looking at it.

Bands step up immediately and step down slowly:
    85+ PURPLE   60+ RED   30+ YELLOW   else GREEN
A band only drops once the score is a clear margin below the threshold, so a
score hovering at 59.8 does not strobe the operator's screen between YELLOW and
GREEN. Raise fast, lower slow.

Usage:
    python risk_engine.py --mqtt-host 127.0.0.1 --serial /dev/ttyACM0
    python risk_engine.py --no-serial --verbose
    python risk_engine.py --selftest        # exercise the maths, no hardware
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from ultron import (  # noqa: E402  (path is set up on the line above)
    BAND_THRESHOLDS,
    RISK_WEIGHTS,
    band_for_score,
)

LOG = logging.getLogger("ultron.risk")

VERSION = "0.5.0-phase1"

# BAND_THRESHOLDS, RISK_WEIGHTS and band_for_score are imported from the shared
# node contract (nodes/common/ultron.py) rather than restated here. Two copies
# of "what RED means" is how a dashboard and a shelf display end up disagreeing
# while both insist they are correct.

HYSTERESIS = 2.0      # a band must fall this far below its threshold to drop
HALF_LIFE_S = 120.0   # a single event's contribution halves every 2 minutes
TICK_S = 1.0          # internal recompute rate
PUBLISH_MIN_INTERVAL_S = 0.5
SERIAL_HZ = 10.0


@dataclass
class Source:
    """One detection feed's current severity, decaying with age."""

    severity: float = 0.0      # 0.0 - 1.0 at `updated`
    updated: float = 0.0

    def decayed(self, now: float) -> float:
        if self.severity <= 0.0:
            return 0.0
        age = max(0.0, now - self.updated)
        return self.severity * (0.5 ** (age / HALF_LIFE_S))


@dataclass
class Engine:
    """Pure scoring state. No I/O, so it can be tested without a broker."""

    sources: dict[str, Source] = field(
        default_factory=lambda: {k: Source() for k in RISK_WEIGHTS}
    )
    band: str = "GREEN"
    score: float = 0.0

    def observe(self, source: str, severity: float, now: float) -> None:
        """Fold in one detection event.

        `severity` is the source's own 0-1 confidence that this matters, not a
        raw packet count: the collectors normalise before publishing.
        """
        if source not in self.sources:
            LOG.debug("ignoring unknown source %r", source)
            return
        severity = max(0.0, min(1.0, severity))
        src = self.sources[source]
        # Take the worst of what we knew and what just arrived: a second,
        # milder event must not overwrite a serious one that is still fresh.
        src.severity = max(src.decayed(now), severity)
        src.updated = now

    def raw_score(self, now: float) -> float:
        total = sum(
            RISK_WEIGHTS[name] * src.decayed(now)
            for name, src in self.sources.items()
        )
        return max(0.0, min(100.0, total * 100.0))

    def step(self, now: float) -> tuple[float, str, bool]:
        """Recompute. Returns (score, band, changed)."""
        score = self.raw_score(now)
        before = (self.score, self.band)

        # Hysteresis: accept any rise, but require a clear fall before dropping
        # a band. Without this the display flickers at a threshold boundary.
        candidate = band_for_score(score)
        # BAND_THRESHOLDS runs highest-first, so a *lower* index means a more
        # severe band.
        order = [name for _, name in BAND_THRESHOLDS]
        cur_i, cand_i = order.index(self.band), order.index(candidate)

        if cand_i < cur_i:
            # Any rise is taken immediately: if the evidence says the house is
            # in more danger, the operator hears about it without delay.
            self.band = candidate
        elif cand_i > cur_i:
            # Drops wait for a clear margin below the threshold being left, so
            # a score resting on a boundary cannot strobe the display.
            threshold = next(t for t, n in BAND_THRESHOLDS if n == self.band)
            if score < (threshold - HYSTERESIS):
                self.band = candidate

        self.score = score
        return score, self.band, before != (self.score, self.band)


# ── severity normalisation ───────────────────────────────────────────────────
# The collectors publish raw observations; turning them into 0-1 confidence
# lives here so every source is scored consistently.

SURICATA_SEVERITY = {"info": 0.2, "yellow": 0.5, "red": 0.8, "purple": 1.0}
# A case physically opened is the least ambiguous signal this appliance has,
# and it comes from the one sensor that cannot be disarmed remotely. It carries
# full confidence on purpose: at 0.9 it scored 27 and the appliance could have
# its own lid torn off while still reporting GREEN.
TRIPWIRE_SEVERITY = 1.0
WIFI_SEVERITY = {"info": 0.3, "yellow": 0.5, "red": 0.7, "purple": 1.0}
LAN_SEVERITY_UNKNOWN = 0.35  # an unfamiliar MAC is a prompt to look, not an alarm


def severity_from_envelope(topic: str, data: dict) -> tuple[str, float] | None:
    """Map an ultron/# MQTT payload onto (source, severity).

    Returns None for anything that is not a scored detection input.
    """
    if topic.startswith("ultron/suricata/"):
        sev = str(data.get("severity") or data.get("sev") or "info").lower()
        return "suricata", SURICATA_SEVERITY.get(sev, 0.5)

    if topic.startswith("ultron/tripwire/"):
        edge = str(data.get("edge") or "").lower()
        if edge == "close":
            return None            # closing a case is not a detection event
        return "tripwire", TRIPWIRE_SEVERITY

    if topic.startswith("ultron/wifi/"):
        sev = str(data.get("severity") or data.get("sev") or "info").lower()
        return "wifi", WIFI_SEVERITY.get(sev, 0.5)

    if topic.startswith("ultron/lan/"):
        if data.get("known", True):
            return None            # known endpoints never move the score
        return "lan", LAN_SEVERITY_UNKNOWN

    return None


# ── I/O ──────────────────────────────────────────────────────────────────────

class Publisher:
    """Publishes score/band to MQTT and streams the same to the C3 over USB."""

    def __init__(self, mqtt_host: str, mqtt_port: int, user: str | None,
                 password: str | None, serial_path: str | None) -> None:
        import paho.mqtt.client as mqtt

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="ultron-risk")
        if user:
            self.client.username_pw_set(user, password or "")
        self.client.connect(mqtt_host, mqtt_port, keepalive=30)
        self.client.loop_start()

        self.serial = None
        if serial_path:
            try:
                self.serial = open(serial_path, "w", buffering=1)  # noqa: SIM115
                LOG.info("indicator link open on %s", serial_path)
            except OSError as exc:
                # A missing indicator must not stop the appliance from scoring:
                # the shelf display is an output, not a dependency.
                LOG.warning("indicator unavailable on %s (%s) — continuing",
                            serial_path, exc)

        self._last_pub = 0.0
        self._last_ser = 0.0

    def publish(self, score: float, band: str, open_alerts: int, msg: str = "") -> None:
        rounded = int(round(score))
        now = time.monotonic()

        if (now - self._last_pub) >= PUBLISH_MIN_INTERVAL_S:
            self._last_pub = now
            self.client.publish("ultron/risk/score", json.dumps({"v": rounded}),
                                qos=1, retain=True)
            self.client.publish("ultron/risk/band", json.dumps({"b": band}),
                                qos=1, retain=True)

        if self.serial and (now - self._last_ser) >= (1.0 / SERIAL_HZ):
            self._last_ser = now
            payload = json.dumps({"score": rounded, "band": band,
                                  "open": open_alerts, "msg": msg[:60]})
            try:
                self.serial.write(payload + "\n")
            except OSError:
                LOG.warning("indicator link lost; closing it")
                self.serial.close()
                self.serial = None

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        if self.serial:
            self.serial.close()


# ── selftest ─────────────────────────────────────────────────────────────────

def selftest() -> int:
    """Exercise the maths with no broker, no serial and no hardware."""
    failures = 0

    def check(label: str, got: object, want: object) -> None:
        nonlocal failures
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {label}: got {got!r} want {want!r}")

    print("bands")
    check("band_for_score(0)", band_for_score(0), "GREEN")
    check("band_for_score(29.9)", band_for_score(29.9), "GREEN")
    check("band_for_score(30)", band_for_score(30), "YELLOW")
    check("band_for_score(60)", band_for_score(60), "RED")
    check("band_for_score(85)", band_for_score(85), "PURPLE")

    print("severity mapping")
    check("suricata red", severity_from_envelope("ultron/suricata/x", {"severity": "red"}),
          ("suricata", 0.8))
    check("tripwire open", severity_from_envelope("ultron/tripwire/pi3a", {"edge": "open"}),
          ("tripwire", 1.0))
    check("tripwire close ignored",
          severity_from_envelope("ultron/tripwire/pi3a", {"edge": "close"}), None)
    check("known LAN ignored",
          severity_from_envelope("ultron/lan/aabb", {"known": True}), None)
    check("unknown LAN", severity_from_envelope("ultron/lan/aabb", {"known": False}),
          ("lan", 0.35))
    check("unknown topic", severity_from_envelope("ultron/health/pi4", {}), None)

    print("weights total 1.0")
    check("sum", round(sum(RISK_WEIGHTS.values()), 6), 1.0)

    print("score maths")
    t = 1_000_000.0
    e = Engine()
    check("idle score", e.raw_score(t), 0.0)

    # A full-confidence Suricata hit is worth exactly its weight.
    e2 = Engine()
    e2.observe("suricata", 1.0, t)
    check("suricata alone", round(e2.raw_score(t), 2), 40.0)

    # ... and halves after one half-life.
    check("suricata after 1 half-life",
          round(e2.raw_score(t + HALF_LIFE_S), 2), 20.0)
    check("suricata after 2 half-lives",
          round(e2.raw_score(t + 2 * HALF_LIFE_S), 2), 10.0)

    # Tripwire + Suricata + rogue WiFi saturates to 100 (allow slight rounding).
    e3 = Engine()
    e3.observe("suricata", 1.0, t)
    e3.observe("tripwire", 1.0, t)
    e3.observe("wifi", 1.0, t)
    e3.observe("lan", 1.0, t)
    check("all sources saturated", round(e3.raw_score(t), 2), 100.0)
    check("all sources => PURPLE", band_for_score(e3.raw_score(t)), "PURPLE")

    print("hysteresis")
    e4 = Engine()
    e4.observe("tripwire", 1.0, t)
    score, band, _ = e4.step(t)
    check("tripwire trips YELLOW", band, "YELLOW")
    # A lone case-open must cross the YELLOW threshold on its own (30.0).
    # At severity 0.9 it scored 27 and sat in GREEN, which meant the appliance
    # could have its own lid prised off while the shelf displayed "all clear".
    check("tripwire alone reaches the threshold", round(score, 2), 30.0)
    # 30 * 0.5^(t/HALF_LIFE): just under the threshold but within the margin,
    # so the band must hold rather than flicker down.
    just_under = t + HALF_LIFE_S * 0.05
    score, band, _ = e4.step(just_under)
    check("band holds inside the hysteresis margin", band, "YELLOW")
    score, band, _ = e4.step(t + 4 * HALF_LIFE_S)
    check("band falls once clearly clear", band, "GREEN")

    print("a milder event does not erase a fresh serious one")
    e5 = Engine()
    e5.observe("suricata", 1.0, t)
    e5.observe("suricata", 0.2, t + 1.0)
    # The second event must not overwrite the first. Note it is not exactly
    # 40.0: the serious reading is compared *after* one second of decay, which
    # is the point — recency is measured, not assumed.
    check("worst-of is kept", round(e5.raw_score(t + 1.0), 2), 39.77)

    print()
    if failures:
        print(f"{failures} check(s) FAILED")
    else:
        print("risk engine selftest: all checks passed")
    return 1 if failures else 0


# ── main loop ────────────────────────────────────────────────────────────────

def run(args: argparse.Namespace) -> int:
    import paho.mqtt.client as mqtt

    engine = Engine()
    pub = Publisher(args.mqtt_host, args.mqtt_port, args.user, args.password,
                    None if args.no_serial else args.serial)
    open_alerts = 0
    last_msg = ""

    def on_message(client, userdata, msg) -> None:  # noqa: ANN001 - paho callback
        nonlocal open_alerts, last_msg
        try:
            data = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError):
            return                      # a malformed frame is not a detection

        if msg.topic.startswith("ultron/alert/"):
            open_alerts += 0 if data.get("ack") else 1
            last_msg = str(data.get("title") or "")
            return

        mapped = severity_from_envelope(msg.topic, data)
        if mapped is None:
            return
        source, severity = mapped
        engine.observe(source, severity, time.monotonic())
        last_msg = str(data.get("signature") or data.get("title") or source)
        if args.verbose:
            LOG.info("%s -> %s %.2f", msg.topic, source, severity)

    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ultron-risk-sub")
    if args.user:
        sub.username_pw_set(args.user, args.password or "")
    sub.on_message = on_message
    sub.connect(args.mqtt_host, args.mqtt_port, keepalive=30)
    sub.subscribe("ultron/#", qos=1)
    sub.loop_start()
    LOG.info("risk engine up — weights %s",
             ", ".join(f"{k}:{v}" for k, v in RISK_WEIGHTS.items()))

    try:
        while True:
            score, band, changed = engine.step(time.monotonic())
            if changed or args.verbose:
                LOG.info("score=%d band=%s open=%d", round(score), band, open_alerts)
            pub.publish(score, band, open_alerts, last_msg)
            time.sleep(TICK_S)
    except KeyboardInterrupt:
        LOG.info("stopping risk engine")
    finally:
        sub.loop_stop()
        sub.disconnect()
        pub.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ULTRON risk engine (Pi4 governance)")
    ap.add_argument("--mqtt-host", default="127.0.0.1")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--user", default=None)
    ap.add_argument("--pass", dest="password", default=None)
    ap.add_argument("--serial", default="/dev/ttyACM0",
                    help="ESP32-C3 indicator link (Pi4 USB 2.0)")
    ap.add_argument("--no-serial", action="store_true",
                    help="run without the shelf indicator attached")
    ap.add_argument("--selftest", action="store_true",
                    help="exercise the scoring maths and exit")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.selftest:
        return selftest()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
