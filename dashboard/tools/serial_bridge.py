#!/usr/bin/env python3
"""ULTRON — USB serial bridge for the ESP32-C3 indicator.

The indicator reads newline-delimited JSON on its USB port. When the board is
cabled to the machine running the dashboard there is no Pi4 to write that
link, so this mirrors the broker onto the panel instead: subscribe to the same
data the dashboard renders, and emit exactly the frame the firmware documents.

`ultron/risk/frame` is preferred when it is being published, because it is the
whole panel -- score, band, the unacknowledged alert count and the message
tail -- and it is the same object nodes/pi4/risk_engine.py writes down the
serial link on the real rig. The older `ultron/risk/score` and
`ultron/risk/band` pair is still understood, so the bridge works against a
broker that only publishes those, but it cannot fill in the other two fields
and will not invent them.

Why USB and not the board's own radio: the demo AP is 5 GHz and the ESP32-C3
is 2.4 GHz-only, so the board cannot associate at all. USB is not a downgrade
here — it is the one transport that definitely works.

DEV-ONLY. Run it with the system python, which carries pyserial:

    /usr/bin/python3 dashboard/tools/serial_bridge.py --port /dev/ttyUSB0

Stop with Ctrl+C.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

import serial


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="/dev/ttyUSB0", help="serial device")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--broker", default="127.0.0.1", help="MQTT host")
    ap.add_argument("--topic-frame", default="ultron/risk/frame")
    ap.add_argument("--topic-score", default="ultron/risk/score")
    ap.add_argument("--topic-band", default="ultron/risk/band")
    ap.add_argument("--quiet", action="store_true", help="do not log each frame")
    return ap.parse_args(argv)


def open_link(port: str, baud: int) -> serial.Serial:
    """Open the port and pulse the reset lines, leaving the board running.

    Opening alone is not enough: the auto-reset wiring can hold the chip in
    reset or drop it into the bootloader. This is the same sequence that works
    when reading a boot log off the same board.
    """
    link = serial.Serial(port, baud, timeout=0.2)
    link.setDTR(False)
    link.setRTS(True)
    time.sleep(0.15)
    link.setRTS(False)
    return link


def whole_panel(doc: dict) -> str | None:
    """Render the feed's full frame, or None if it is not usable.

    Every field is checked rather than coerced. The panel is what the operator
    reads off the shelf, so a board showing an invented number is worse than one
    admitting it has nothing.
    """
    score = doc.get("score")
    band = doc.get("band")
    if isinstance(score, bool) or not isinstance(score, int):
        return None
    if not isinstance(band, str) or not band:
        return None

    opened = doc.get("open")
    msg = doc.get("msg")
    return json.dumps(
        {
            "score": max(0, min(100, score)),
            "band": band,
            "open": opened if isinstance(opened, int) and not isinstance(opened, bool) else 0,
            "msg": msg[:60] if isinstance(msg, str) else "",
        },
        separators=(",", ":"),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    score: int | None = None
    band: str | None = None
    seen_frame = False
    link: serial.Serial | None = None

    while True:
        try:
            if link is None:
                link = open_link(args.port, args.baud)
                print(f"[bridge] {args.port} open at {args.baud}", flush=True)

            sub = subprocess.Popen(
                [
                    "mosquitto_sub",
                    "-h", args.broker,
                    # -v so the topics can be told apart: `frame` carries the
                    # whole panel, score and band only the two halves of it.
                    "-v",
                    "-t", args.topic_frame,
                    "-t", args.topic_score,
                    "-t", args.topic_band,
                ],
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert sub.stdout is not None

            for raw in sub.stdout:
                raw = raw.strip()
                if not raw:
                    continue
                topic, _, body = raw.partition(" ")
                try:
                    doc = json.loads(body)
                except json.JSONDecodeError:
                    continue

                if topic.endswith("/frame"):
                    out = whole_panel(doc)
                    if out is None:
                        continue
                    seen_frame = True
                elif seen_frame:
                    # A full frame is already arriving once a second. Score and
                    # band are the same data in halves and would only double the
                    # writes onto a 4 Hz-limited panel.
                    continue
                else:
                    if isinstance(doc.get("v"), int):
                        score = doc["v"]
                    if isinstance(doc.get("b"), str):
                        band = doc["b"]

                    # Nothing to show until both halves have arrived at least once.
                    if score is None or band is None:
                        continue

                    # open/msg stay blank on this path: score and band genuinely
                    # do not carry them, and inventing an alert count on the
                    # panel would be a lie.
                    out = json.dumps(
                        {"score": score, "band": band, "open": 0, "msg": ""},
                        separators=(",", ":"),
                    )

                link.write((out + "\n").encode())
                if not args.quiet:
                    print(f"[bridge] -> {out}", flush=True)

        except KeyboardInterrupt:
            break
        except (OSError, serial.SerialException) as exc:
            print(f"[bridge] {exc}; retrying in 2s", flush=True)
            try:
                if link is not None:
                    link.close()
            except Exception:
                pass
            link = None
            time.sleep(2)

    if link is not None:
        try:
            link.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
