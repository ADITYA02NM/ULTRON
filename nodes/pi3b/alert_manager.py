#!/usr/bin/env python3
"""ULTRON alert manager — Pi3b ALERT.

The only process in the appliance that writes to the evidence vault. Every other
node treats it as read-only, which is what makes the record trustworthy: a
compromised detection node cannot quietly delete the alert that named it.

Responsibilities
  1. Persist every alert and every band change to the evidence database.
  2. Notify on RED and PURPLE transitions (Phase 1 is notify-only — no
     blocking). Mail and an optional push relay are both off until configured;
     with neither set, nothing ever leaves the LAN.
  3. Own acknowledgement: the operator ACKs in the dashboard, and this node is
     what makes it stick, writing `ack`/`ack_ts` and re-publishing the alert so
     the UI reflects the durable record rather than a hopeful local guess.

Usage:
    python alert_manager.py --db /mnt/pendrive/ultron/ultron.db
    python alert_manager.py --db ./dev-evidence.db --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import smtplib
import sqlite3
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from ultron import (  # noqa: E402
    TOPIC_ACK,
    TOPIC_ALERT,
    TOPIC_BAND,
    TOPIC_SCORE,
    Link,
    add_mqtt_args,
    fail,
    setup_logging,
)

LOG = logging.getLogger("ultron.alert")

# Only these bands are worth waking someone for. YELLOW is recorded and shown,
# but a notification that fires on YELLOW trains the operator to ignore it.
NOTIFY_BANDS = {"RED", "PURPLE"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id      TEXT PRIMARY KEY,
    ts      INTEGER NOT NULL,
    sev     TEXT,
    title   TEXT,
    src     TEXT,
    body    TEXT,
    ack     INTEGER NOT NULL DEFAULT 0,
    ack_ts  INTEGER
);
CREATE TABLE IF NOT EXISTS scores (
    ts      INTEGER NOT NULL,
    score   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);
CREATE INDEX IF NOT EXISTS idx_scores_ts ON scores (ts DESC);
"""


class Vault:
    """Append-only evidence store."""

    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # paho delivers messages on its own network thread, so every write below
        # runs on that thread while this connection was created on the main one.
        # Without check_same_thread=False sqlite refuses the first message --
        # "SQLite objects created in a thread can only be used in that same
        # thread" -- and the node dies before it records anything, let alone
        # notifies. The lock is what makes the sharing safe: sqlite is still not
        # thread-safe, so the callback thread and the shutdown path must never
        # be inside a transaction at the same time.
        self.db = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            self.db.commit()

    def record_alert(self, data: dict) -> None:
        alert_id = str(data.get("id") or "")
        if not alert_id:
            LOG.warning("dropping alert with no id: %r", data)
            return
        with self._lock:
            self.db.execute(
                "INSERT OR IGNORE INTO alerts"
                " (id, ts, sev, title, src, body, ack, ack_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (alert_id, int(data.get("ts") or time.time()),
                 data.get("sev") or "info", data.get("title") or "",
                 data.get("src") or "", data.get("body") or "",
                 1 if data.get("ack") else 0, data.get("ack_ts")),
            )
            self.db.commit()

    def acknowledge(self, alert_id: str) -> bool:
        """Mark an alert acknowledged. Returns True if this call changed it."""
        with self._lock:
            cur = self.db.execute(
                "UPDATE alerts SET ack = 1, ack_ts = ? WHERE id = ? AND ack = 0",
                (int(time.time()), alert_id),
            )
            self.db.commit()
            return cur.rowcount > 0

    def find_alert(self, alert_id: str) -> dict | None:
        with self._lock:
            row = self.db.execute(
                "SELECT id, ts, sev, title, src, body, ack, ack_ts"
                " FROM alerts WHERE id = ?",
                (alert_id,),
            ).fetchone()
        if row is None:
            return None
        keys = ("id", "ts", "sev", "title", "src", "body", "ack", "ack_ts")
        out = dict(zip(keys, row, strict=True))
        out["ack"] = bool(out["ack"])
        return out

    def record_score(self, score: int, ts: int | None = None) -> None:
        with self._lock:
            self.db.execute("INSERT INTO scores (ts, score) VALUES (?, ?)",
                            (ts or int(time.time()), int(score)))
            self.db.commit()

    def close(self) -> None:
        with self._lock:
            self.db.close()


def send_mail(args: argparse.Namespace, subject: str, body: str) -> None:
    if args.dry_run or not args.smtp_host:
        LOG.info("[mail suppressed] %s — %s", subject, body)
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = args.mail_from
    msg["To"] = ", ".join(args.mail_to)
    msg.set_content(body)
    try:
        with smtplib.SMTP(args.smtp_host, args.smtp_port, timeout=15) as smtp:
            if args.smtp_user:
                # starttls() with no context uses ssl._create_stdlib_context(),
                # which checks nothing: no certificate verification, no hostname
                # check. We are one line away from handing that socket an app
                # password, so we make it prove who it is first.
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(args.smtp_user, args.smtp_pass or "")
            smtp.send_message(msg)
        LOG.info("notified %s: %s", ", ".join(args.mail_to), subject)
    except OSError as exc:
        # A failed notification must not stop the vault being written.
        LOG.error("could not send notification: %s", exc)


def push_band(args: argparse.Namespace, band: str, subject: str, body: str) -> None:
    """Push a notification to an ntfy-compatible server.

    This is the only path by which alert content can leave the LAN, so it stays
    off until an operator names a topic. No topic, nothing dialled — which is
    what keeps the appliance's zero-cloud claim honest for anyone who has not
    asked for push.
    """
    if not args.push_topic:
        return
    if args.dry_run:
        LOG.info("[push suppressed] %s — %s", subject, body)
        return
    url = f"{args.push_url.rstrip('/')}/{urllib.parse.quote(args.push_topic)}"
    req = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Title": subject,
            "Priority": "urgent" if band == "PURPLE" else "high",
            "Tags": "rotating_light" if band == "PURPLE" else "warning",
            "Markdown": "no",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        LOG.info("pushed %s: %s", args.push_topic, subject)
    except OSError as exc:
        # Same rule as mail: urllib.error.URLError and HTTPError both derive
        # from OSError, so a dead push relay costs a notification, never the
        # record, and never the process.
        LOG.error("could not push notification: %s", exc)


def run(args: argparse.Namespace) -> int:
    vault = Vault(args.db)
    link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                "ultron-alerts")
    LOG.info("alert manager up — vault %s", args.db)

    state = {"band": "GREEN"}
    push_bands = {b.strip().upper()
                  for b in (args.push_bands or "").split(",") if b.strip()}

    def on_message(client, userdata, msg) -> None:  # noqa: ANN001 - paho callback
        try:
            data = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError):
            return

        if msg.topic.startswith(TOPIC_ALERT + "/"):
            data.setdefault("id", msg.topic.rsplit("/", 1)[-1])
            vault.record_alert(data)
            LOG.info("recorded %s [%s] %s", data["id"], data.get("sev"),
                     data.get("title"))
            return

        if msg.topic == TOPIC_SCORE:
            value = data.get("v")
            if isinstance(value, (int, float)):
                vault.record_score(int(value))
            return

        if msg.topic == TOPIC_BAND:
            band = str(data.get("b") or "").upper()
            if band and band != state["band"]:
                LOG.info("band %s -> %s", state["band"], band)
                state["band"] = band
                subject = f"ULTRON {band}"
                body = (f"Risk band is now {band}.\n"
                        f"Open the dashboard to review and acknowledge.")
                if band in NOTIFY_BANDS:
                    send_mail(args, subject, body)
                if band in push_bands:
                    push_band(args, band, subject, body)
            return

        if msg.topic.startswith(TOPIC_ACK + "/"):
            alert_id = msg.topic.rsplit("/", 1)[-1]
            if not vault.acknowledge(alert_id):
                return
            stored = vault.find_alert(alert_id)
            if stored:
                # Re-publish so the dashboard shows the durable record rather
                # than trusting its own optimistic local update.
                link.publish(f"{TOPIC_ALERT}/{alert_id}", stored)
                LOG.info("acknowledged %s (durable)", alert_id)

    link.on_message(on_message)
    link.subscribe("ultron/#", qos=1)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("stopping alert manager")
    finally:
        link.stop()
        vault.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ULTRON alert manager (Pi3b alert)")
    ap.add_argument("--db", default="/mnt/pendrive/ultron/ultron.db",
                    help="evidence vault (this node is its only writer)")
    ap.add_argument("--dry-run", action="store_true",
                    help="record everything but send no mail and no push")
    ap.add_argument("--smtp-host", default=None)
    ap.add_argument("--smtp-port", type=int, default=587)
    ap.add_argument("--smtp-user", default=None)
    ap.add_argument("--smtp-pass", dest="smtp_pass", default=None)
    ap.add_argument("--mail-from", default="ultron@localhost")
    ap.add_argument("--mail-to", action="append", default=[],
                    help="repeat for several recipients")
    ap.add_argument("--push-url", default="https://ntfy.sh",
                    help="ntfy-compatible push server")
    ap.add_argument("--push-topic", default=None,
                    help="push topic; unset means no push at all")
    ap.add_argument("--push-bands", default="RED,PURPLE",
                    help="comma-separated bands that push a notification")
    add_mqtt_args(ap)
    args = ap.parse_args(argv)
    setup_logging(args.verbose)

    if not args.db:
        return fail("an evidence vault path is required")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
