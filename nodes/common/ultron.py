"""ULTRON node contract — shared by every Pi-side service.

One place defines the band thresholds, the risk weights and the topic names, so
no two nodes can quietly disagree about what "RED" means. The governance node's
risk engine was made deliberately self-contained to keep the scoring maths
testable on its own; the thresholds and weights it uses are re-exported here
rather than restated, and `nodes/tests/test_ultron_contract.py` fails if the two
ever drift apart.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

LOG = logging.getLogger("ultron.node")

VERSION = "0.5.0-phase1"

# Descending: index 0 is the most severe band.
BAND_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (85, "PURPLE"),
    (60, "RED"),
    (30, "YELLOW"),
    (0, "GREEN"),
)

# Documented weights. They must total 1.0 or the score cannot reach 100 and
# every PURPLE response in the runbook becomes unreachable.
RISK_WEIGHTS: dict[str, float] = {
    "suricata": 0.40,
    "tripwire": 0.30,
    "wifi": 0.20,
    "lan": 0.10,
}

# ── topics ───────────────────────────────────────────────────────────────────
TOPIC_SCORE = "ultron/risk/score"
TOPIC_BAND = "ultron/risk/band"
TOPIC_ALERT = "ultron/alert"
TOPIC_HEALTH = "ultron/health"
TOPIC_LAN = "ultron/lan"
TOPIC_TRIPWIRE = "ultron/tripwire"
TOPIC_SURICATA = "ultron/suricata"
TOPIC_WIFI = "ultron/wifi"
TOPIC_ACK = "ultron/ack"


def band_for_score(score: float) -> str:
    for threshold, name in BAND_THRESHOLDS:
        if score >= threshold:
            return name
    return "GREEN"


def lan_topic(mac: str) -> str:
    return TOPIC_LAN + "/" + mac.replace(":", "").replace("-", "").lower()


# ── MQTT ─────────────────────────────────────────────────────────────────────

def add_mqtt_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--user", default=None)
    parser.add_argument("--pass", dest="password", default=None)
    parser.add_argument("--verbose", action="store_true")


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class Link:
    """Thin MQTT wrapper: one connection, JSON payloads, clean shutdown."""

    def __init__(self, host: str, port: int, user: str | None,
                 password: str | None, client_id: str) -> None:
        import paho.mqtt.client as mqtt

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                   client_id=client_id)
        if user:
            self._client.username_pw_set(user, password or "")
        self._client.connect(host, port, keepalive=30)
        self._client.loop_start()

    @property
    def client(self):
        return self._client

    def publish(self, topic: str, payload: dict | str, *, retain: bool = False,
                qos: int = 1) -> None:
        data = payload if isinstance(payload, str) else json.dumps(payload)
        self._client.publish(topic, data, qos=qos, retain=retain)

    def on_message(self, fn) -> None:
        self._client.on_message = fn

    def subscribe(self, topic: str, qos: int = 1) -> None:
        self._client.subscribe(topic, qos=qos)

    def stop(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            pass


def fail(message: str, code: int = 1) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


def require_file(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"error: {path} does not exist")
    return p
