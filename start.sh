#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ULTRON — one-command local stack (no sudo, no Docker, no Raspberry Pi)
#
#   ./start.sh              mqtt + backend :8081 + vite :5173 + mock feed
#   ./start.sh --prod       mqtt + backend :8080 serving the prebuilt dist
#   ./start.sh --fresh      wipe auth.db first so the QR enrols a new passkey
#   ./start.sh --no-feed    skip the mock sensor publisher
#   ./start.sh --no-qr      skip QR generation
#
# Ctrl+C stops every child this script started.
# ---------------------------------------------------------------------------
set -euo pipefail

VITE_PORT="${ULTRON_VITE_PORT:-5173}"

# True when whatever is listening on $1 belongs to THIS repo. Without this the
# launcher happily "reuses" another project's server and then serves the wrong
# app to the browser while reporting everything healthy.
port_is_ours() {
  local port="$1" pid cwd
  pid="$(ss -ltnp 2>/dev/null | grep ":$port " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)"
  [ -n "$pid" ] || return 1
  cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
  case "$cwd" in "$REPO"*) return 0 ;; esac
  return 1
}


REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="$REPO/.venv/bin/python"
DASH="$REPO/dashboard"
LOG="/tmp/ultron"

MODE="dev"
FRESH=0
FEED=1
QR=1

usage() {
  cat <<'EOF'
ULTRON — one-command local stack (no sudo, no Docker, no Raspberry Pi)

  ./start.sh              mqtt + backend :8081 + vite :5173 + mock feed
  ./start.sh --prod       mqtt + backend :8080 serving the prebuilt dist
  ./start.sh --fresh      wipe auth.db first so the QR enrols a new passkey
  ./start.sh --no-feed    skip the mock sensor publisher
  ./start.sh --no-qr      skip QR generation
  ./start.sh --help       this text

Ctrl+C stops every child this script started. Logs land in /tmp/ultron-*.log
EOF
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --prod)    MODE="prod" ;;
    --fresh)   FRESH=1 ;;
    --no-feed) FEED=0 ;;
    --no-qr)   QR=0 ;;
    -h|--help) usage ;;
    *) echo "start.sh: unknown flag: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# --- port topology ---------------------------------------------------------
if [ "$MODE" = "prod" ]; then
  HTTP_PORT=8080
  ORIGINS="http://localhost:8080,http://localhost:8081,http://localhost:5173"
else
  HTTP_PORT=8081
  ORIGINS="http://localhost:5173,http://localhost:8081,http://localhost:8080"
fi

# --- child bookkeeping -----------------------------------------------------
PIDS=()

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "[start] stopping ..."
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] || continue
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 0.4
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] || continue
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  done
  echo "[start] stopped."
}
trap cleanup INT TERM EXIT

# start_bg <name> <workdir> <cmd...>
# Runs cmd from <workdir> in its own process group (so cleanup can kill the
# whole tree), logging to /tmp/ultron-<name>.log.
start_bg() {
  local name="$1" dir="$2"; shift 2
  setsid bash -c 'cd "$1" || exit 1; shift; exec "$@"' _ "$dir" "$@" \
    >"$LOG-$name.log" 2>&1 &
  local pid=$!
  PIDS+=("$pid")
  echo "[start] $name -> pid $pid (log $LOG-$name.log)"
}

# 0 = both 127.0.0.1 and ::1 are free for the port, 1 = something is bound
port_free() {
  "$PY" - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
for host in ("127.0.0.1", "::1"):
    fam = socket.AF_INET6 if ":" in host else socket.AF_INET
    s = socket.socket(fam, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
    except OSError:
        sys.exit(1)
    finally:
        s.close()
sys.exit(0)
PY
}

# ---------------------------------------------------------------------------
# 1. Python environment
# ---------------------------------------------------------------------------
if [ ! -x "$PY" ]; then
  echo "[start] creating .venv ..."
  python3 -m venv "$REPO/.venv"
fi
if ! "$PY" -c 'import aiohttp, aiomqtt, aiosqlite, webauthn, paho.mqtt' 2>/dev/null; then
  echo "[start] installing server deps ..."
  "$PY" -m pip install -q -r "$DASH/server/requirements.txt"
fi
if [ "$QR" = 1 ] && ! "$PY" -c 'import segno' 2>/dev/null; then
  echo "[start] installing segno (QR renderer) ..."
  "$PY" -m pip install -q segno
fi

if [ ! -d "$DASH/web/node_modules" ]; then
  echo "[start] installing frontend deps ..."
  (cd "$DASH/web" && npm install)
fi

# ---------------------------------------------------------------------------
# 2. MQTT broker (user-level, no sudo)
# ---------------------------------------------------------------------------
if port_free 1883; then
  start_bg mqtt "$REPO" mosquitto -c "$REPO/tools/mosquitto.dev.conf"
  echo -n "[start] mqtt 127.0.0.1:1883"
  ok=0
  for _ in $(seq 1 40); do
    if ! port_free 1883; then ok=1; break; fi   # bound == up
    echo -n "."
    sleep 0.25
  done
  echo
  if [ "$ok" != 1 ]; then
    echo "[start] mosquitto failed to bind 1883 — see $LOG-mqtt.log" >&2
    tail -20 "$LOG-mqtt.log" >&2 || true
    exit 1
  fi
  echo "[start] mqtt broker up"
else
  echo "[start] mqtt: 1883 already in use, reusing the existing broker"
fi

# ---------------------------------------------------------------------------
# 2b. LAN demo rig: a stable access code + this machine's LAN address
# ---------------------------------------------------------------------------
DEMO_CODE_FILE="$REPO/.demo-code"
DEMO_CODE="${ULTRON_DEMO_CODE:-}"
if [ -z "$DEMO_CODE" ] && [ -f "$DEMO_CODE_FILE" ]; then
  DEMO_CODE="$(cat "$DEMO_CODE_FILE" 2>/dev/null || true)"
fi
if [ -z "$DEMO_CODE" ]; then
  DEMO_CODE="$(od -An -N4 -tx4 /dev/urandom | tr -d ' \n' | tr 'a-f' 'A-F')"
  printf '%s' "$DEMO_CODE" > "$DEMO_CODE_FILE"
fi

# Pick this machine's real LAN address. A container/VM bridge (docker0, br-*,
# veth*, virbr*, vmnet*, tailscale0 …) is routable from this host but invisible
# to a phone on the Wi-Fi, which is exactly who needs this URL — so ask the
# kernel which source address the default route uses, and only fall back to a
# filtered interface scan.
_lan_ip() {
  local ip=""
  ip="$(ip -4 route get 1.1.1.1 2>/dev/null \
        | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')"
  [ -n "$ip" ] || ip="$(ip -4 -o addr show scope global 2>/dev/null \
        | awk '{print $2, $4}' \
        | grep -vE '^(docker|br-|veth|virbr|vmnet|tun|tap|tailscale|zt)' \
        | awk '{print $2}' | cut -d/ -f1 | head -n1)"
  [ -n "$ip" ] || ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "$ip" ] || ip="127.0.0.1"
  printf '%s' "$ip"
}
LAN_IP="$(_lan_ip)"
case ",$ORIGINS," in
  *",http://$LAN_IP:$HTTP_PORT,"*) : ;;
  *) ORIGINS="$ORIGINS,http://$LAN_IP:$HTTP_PORT" ;;
esac

# ---------------------------------------------------------------------------
# 3. Local env the backend expects (must happen before Config.load() is called)
# ---------------------------------------------------------------------------
if [ "$MODE" = "prod" ]; then
  # The whole point of --prod is a phone/2nd laptop on the Wi-Fi reaching the
  # dashboard, so bind every interface. Dev keeps it on the loopback and lets
  # the vite proxy do the talking.
  export ULTRON_HTTP_HOST=0.0.0.0
else
  export ULTRON_HTTP_HOST=127.0.0.1
fi
export ULTRON_HTTP_PORT="$HTTP_PORT"
export ULTRON_MQTT_HOST=127.0.0.1
export ULTRON_MQTT_PORT=1883
export ULTRON_MQTT_USER=""            # anonymous; bridge.py drops auth when empty
export ULTRON_RP_ID=localhost         # must be a hostname — config rejects IPs
export ULTRON_RP_NAME=ULTRON
export ULTRON_ORIGINS="$ORIGINS"      # the vite origin has to be here or the WS upgrade 403s
export ULTRON_EVIDENCE_DB="$REPO/dev-evidence.db"
export ULTRON_DEBUG=1
export ULTRON_ALLOW_LAN=1             # permit the LAN origin added above
export ULTRON_DEMO_CODE="$DEMO_CODE"  # enables /auth/demo + the code prompt

# ---------------------------------------------------------------------------
# 4. Evidence DB (the server only ever reads it; the demo needs it to exist)
# ---------------------------------------------------------------------------
"$PY" - "$ULTRON_EVIDENCE_DB" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.executescript("""
CREATE TABLE IF NOT EXISTS scores (ts INTEGER NOT NULL, score INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY, ts INTEGER NOT NULL, sev TEXT, title TEXT,
    src TEXT, body TEXT, ack INTEGER DEFAULT 0, ack_ts INTEGER);
""")
db.commit()
PY

# ---------------------------------------------------------------------------
# 5. Optional auth reset (so the QR actually reaches the enrolment screen)
# ---------------------------------------------------------------------------
if [ "$FRESH" = 1 ]; then
  if [ -f "$DASH/auth.db" ]; then
    cp "$DASH/auth.db" "$DASH/auth.db.bak.$(date +%Y%m%d-%H%M%S)"
  fi
  (cd "$DASH" && "$PY" -c \
    'from server.auth_db import AuthDB; from server.config import load
db = AuthDB(load().auth_db); db.reset_owner()
print("[start] auth.db reset: no owner, next open = enrolment setup")')
fi

# ---------------------------------------------------------------------------
# 6. Backend
# ---------------------------------------------------------------------------
if ! port_free "$HTTP_PORT" && ! port_is_ours "$HTTP_PORT"; then
  echo "[start] ERROR: port $HTTP_PORT is held by another program, not this repo."
  echo "[start]        Refusing to reuse it - the browser would show the wrong app."
  echo "[start]        Stop that service, or set ULTRON_HTTP_PORT."
  exit 1
fi

if port_free "$HTTP_PORT"; then
  start_bg server "$DASH" "$PY" -m server.main
  echo -n "[start] backend http://localhost:$HTTP_PORT"
  ok=0
  for _ in $(seq 1 60); do
    if curl -sf "http://localhost:$HTTP_PORT/healthz" -o /dev/null 2>/dev/null; then
      ok=1; break
    fi
    echo -n "."
    sleep 0.5
  done
  echo
  if [ "$ok" != 1 ]; then
    echo "[start] backend did not answer /healthz — last 40 log lines:" >&2
    tail -40 "$LOG-server.log" >&2 || true
    exit 1
  fi
  echo "[start] backend healthy"
else
  echo "[start] backend: $HTTP_PORT already in use, reusing it"
fi

# ---------------------------------------------------------------------------
# 7. Frontend
# ---------------------------------------------------------------------------
if [ "$MODE" = "dev" ]; then
    if ! port_free "$VITE_PORT" && ! port_is_ours "$VITE_PORT"; then
    echo "[start] ERROR: port $VITE_PORT is held by another program, not this repo."
    echo "[start]        ULTRON's vite cannot bind, so the browser would show the"
    echo "[start]        wrong app. Stop that service, or set ULTRON_VITE_PORT."
    exit 1
  fi

if port_free "$VITE_PORT"; then
    start_bg vite "$DASH/web" "$DASH/web/node_modules/.bin/vite"
    echo -n "[start] vite http://localhost:$VITE_PORT"
    ok=0
    for _ in $(seq 1 40); do
      if curl -sf "http://localhost:$VITE_PORT/" -o /dev/null 2>/dev/null; then
        ok=1; break
      fi
      echo -n "."
      sleep 0.5
    done
    echo
    if [ "$ok" != 1 ]; then
      echo "[start] vite did not answer — last 40 log lines:" >&2
      tail -40 "$LOG-vite.log" >&2 || true
      exit 1
    fi
    echo "[start] vite healthy"
  else
    echo "[start] vite: $VITE_PORT already in use (ours), reusing it"
  fi
else
  # --prod serves the static bundle, so it has to exist and be current.
  if [ ! -f "$DASH/web/dist/index.html" ]; then
    echo -n "[start] building dist (first run)"
    if (cd "$DASH/web" && npm run build) >"$LOG-build.log" 2>&1; then
      echo " done"
    else
      echo
      echo "[start] build failed — last 30 log lines:" >&2
      tail -30 "$LOG-build.log" >&2 || true
      exit 1
    fi
  else
    echo "[start] dist present (rebuild with: cd dashboard/web && npm run build)"
  fi
fi

# ---------------------------------------------------------------------------
# 8. Mock feed (plays the Pis + the risk engine)
# ---------------------------------------------------------------------------
if [ "$FEED" = 1 ]; then
  start_bg feed "$REPO" "$PY" -u "$DASH/tools/mock_feed.py" --host 127.0.0.1 --port 1883 --script demo
  sleep 1
fi

# ---------------------------------------------------------------------------
# 9. Login / enrolment URL + QR
# ---------------------------------------------------------------------------
TOKEN=""
if [ "$MODE" = "prod" ]; then
  DASH_URL="http://localhost:$HTTP_PORT"
  LAN_NOTE="reachable from your phone/2nd laptop at http://$LAN_IP:$HTTP_PORT"
else
  DASH_URL="http://localhost:$VITE_PORT"
  LAN_NOTE="vite dev binds loopback only — use --prod for the phone"
fi

if [ "$QR" = 1 ]; then
  TOKEN="$(cd "$DASH" && "$PY" -c \
    'from server.auth_db import AuthDB; from server.config import load
print(AuthDB(load().auth_db).create_enrollment_token(ttl=900))')"
  URL="$DASH_URL/?t=$TOKEN"
else
  URL="$DASH_URL/"
fi

cat <<EOF

================================================================
 ULTRON is up
================================================================
  Dashboard   $DASH_URL
  API / WS    http://localhost:$HTTP_PORT   (proxied /ws, /auth, /healthz)
  MQTT        127.0.0.1:1883
$( [ "$FEED" = 1 ] && echo "  Mock feed   demo script, looping forever" )
  LAN code    $DEMO_CODE        (backup sign-in: phone / 2nd laptop)
  LAN URL     http://$LAN_IP:$HTTP_PORT   ($LAN_NOTE)

  Open this to sign in / enrol a passkey (valid ~15 min):
  $URL
EOF

if [ "$QR" = 1 ]; then
  echo
  "$PY" -c 'import segno, sys
segno.make(sys.argv[1], error="m").terminal(out=sys.stdout)' "$URL"
fi

cat <<EOF

  Logs  /tmp/ultron-{mqtt,server,vite,feed}.log
  Stop  Ctrl+C
================================================================

EOF

# ---------------------------------------------------------------------------
# 10. Stay up; exit as soon as any child dies
# ---------------------------------------------------------------------------
if wait -n 2>/dev/null; then
  echo "[start] a component exited — shutting down."
else
  echo "[start] a component exited (rc=$?) — shutting down."
fi
exit 1
