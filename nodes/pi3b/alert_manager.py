#!/usr/bin/env python3
"""ULTRON alert manager — Pi3b ALERT.

The only process in the appliance that writes to the evidence vault. Every other
node treats it as read-only, which is what makes the record trustworthy: a
compromised detection node cannot quietly delete the alert that named it.

Responsibilities
  1. Persist every alert and every band change to the evidence database.
  2. Email RED and PURPLE transitions (Phase 1 is notify-only — no blocking).
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
import sys
import time
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
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def record_alert(self, data: dict) -> None:
        alert_id = str(data.get("id") or "")
        if not alert_id:
            LOG.warning("dropping alert with no id: %r", data)
            return
        self.db.execute(
            "INSERT OR IGNORE INTO alerts (id, ts, sev, title, src, body, ack, ack_ts)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (alert_id, int(data.get("ts") or time.time()),
             data.get("sev") or "info", data.get("title") or "",
             data.get("src") or "", data.get("body") or "",
             1 if data.get("ack") else 0, data.get("ack_ts")),
        )
        self.db.commit()

    def acknowledge(self, alert_id: str) -> bool:
        """Mark an alert acknowledged. Returns True if this call changed it."""
        cur = self.db.execute(
            "UPDATE alerts SET ack = 1, ack_ts = ? WHERE id = ? AND ack = 0",
            (int(time.time()), alert_id),
        )
        self.db.commit()
        return cur.rowcount > 0

    def find_alert(self, alert_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT id, ts, sev, title, src, body, ack, ack_ts FROM alerts WHERE id = ?",
            (alert_id,),
        ).fetchone()
        if row is None:
            return None
        keys = ("id", "ts", "sev", "title", "src", "body", "ack", "ack_ts")
        out = dict(zip(keys, row, strict=True))
        out["ack"] = bool(out["ack"])
        return out

    def record_score(self, score: int, ts: int | None = None) -> None:
        self.db.execute("INSERT INTO scores (ts, score) VALUES (?, ?)",
                        (ts or int(time.time()), int(score)))
        self.db.commit()

    def close(self) -> None:
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
                smtp.starttls()
                smtp.login(args.smtp_user, args.smtp_pass or "")
            smtp.send_message(msg)
        LOG.info("notified %s: %s", ", ".join(args.mail_to), subject)
    except OSError as exc:
        # A failed notification must not stop the vault being written.
        LOG.error("could not send notification: %s", exc)


def run(args: argparse.Namespace) -> int:
    vault = Vault(args.db)
    link = Link(args.mqtt_host, args.mqtt_port, args.user, args.password,
                "ultron-alerts")
    LOG.info("alert manager up — vault %s", args.db)

    state = {"band": "GREEN"}

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
                if band in NOTIFY_BANDS:
                    send_mail(args, f"ULTRON {band}",
                              f"Risk band is now {band}.\n"
                              f"Open the dashboard to review and acknowledge.")
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
                    help="record everything but send no mail")
    ap.add_argument("--smtp-host", default=None)
    ap.add_argument("--smtp-port", type=int, default=587)
    ap.add_argument("--smtp-user", default=None)
    ap.add_argument("--smtp-pass", dest="smtp_pass", default=None)
    ap.add_argument("--mail-from", default="ultron@localhost")
    ap.add_argument("--mail-to", action="append", default=[],
                    help="repeat for several recipients")
    add_mqtt_args(ap)
    args = ap.parse_args(argv)
    setup_logging(args.verbose)

    if not args.db:
        return fail("an evidence vault path is required")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
