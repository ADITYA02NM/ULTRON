#!/usr/bin/env bash
# ULTRON — run the sensor drill by hand.
#
# The dashboard's SIMULATE button does the same thing through the server. This
# script is for when you would rather drive it from a terminal. Either way the
# beats go to MQTT exactly as a real sensor's would, so the dashboard, the
# evidence vault and Pi3b's alert manager all see them — nothing is faked in
# the page.
set -euo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="$REPO/.venv/bin/python"
FEED="$REPO/dashboard/tools/mock_feed.py"

HOST="${ULTRON_MQTT_HOST:-127.0.0.1}"
PORT="${ULTRON_MQTT_PORT:-1883}"

usage() {
  cat <<'EOF'
ULTRON — sensor drill, driven from the terminal.

  ./simulate.sh                    the stress drill, looping until Ctrl+C
  ./simulate.sh demo               the calm home-under-watch story (peaks YELLOW)
  ./simulate.sh stress --cycles 1  one pass through every band, then exit
  ./simulate.sh --help             this text

The stress drill runs every detector the rig has: reconnaissance (YELLOW), a
beacon, unsigned firmware and a CVE (RED), then lateral movement, exfiltration
and containment (PURPLE). It reaches RED about 26 s in and PURPLE about 38 s in,
on a ~56 s cycle.

Mind the notifier: Pi3b emails on every band change into RED or PURPLE, so a
looping drill means roughly three emails per cycle. Use --cycles 1 for a single
controlled pass.

Broker address comes from ULTRON_MQTT_HOST / ULTRON_MQTT_PORT, defaulting to
127.0.0.1:1883. Anything after the script name is passed straight through.
EOF
}

SCRIPT="stress"
if [ "$#" -gt 0 ]; then
  case "$1" in
    -h|--help) usage; exit 0 ;;
    demo|stress) SCRIPT="$1"; shift ;;
    -*) : ;;  # a flag, not a script name — keep the default
    *) echo "simulate.sh: unknown script: $1 (try --help)" >&2; exit 2 ;;
  esac
fi

if [ ! -x "$PY" ]; then
  echo "simulate.sh: no interpreter at $PY — run ./start.sh once to build the venv." >&2
  exit 1
fi
if [ ! -f "$FEED" ]; then
  echo "simulate.sh: mock feed missing at $FEED" >&2
  exit 1
fi

echo "[simulate] $SCRIPT -> mqtt://$HOST:$PORT   (Ctrl+C stops it)"
exec "$PY" -u "$FEED" --host "$HOST" --port "$PORT" --script "$SCRIPT" "$@"
