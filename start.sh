#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ULTRON — one-command local stack (no sudo, no Docker, no Raspberry Pi)
#
#   ./start.sh              mqtt + backend :8081 + vite :5173 (nothing simulated)
#   ./start.sh --feed       also start the mock sensor publisher
#   ./start.sh --prod       mqtt + backend :8080 serving the prebuilt dist
#   ./start.sh --fresh      wipe auth.db first so the QR enrols a new passkey
#   ./start.sh --no-qr      skip QR generation
#
# The sensor simulation is OFF by default. Nothing publishes until an operator
# asks for it, so the dashboard shows the honest state -- quiet, and stale if
# nothing has reported -- instead of a demo already in progress. Use
# ./simulate.sh to drive it; see that script for the two scenarios.
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

# Nothing is simulated unless an operator asks for it. A dashboard bolted to a
# quiet broker is the honest picture; a demo that is already in progress is not.
FEED=0
QR=1
# The port-sweep sensor is part of the live console, not an add-on: without it a
# real nmap scan is invisible, which is the first thing a visitor tries. It needs
# CAP_NET_RAW, so it is skipped with a warning when tcpdump cannot capture.
SCAN=1

usage() {
  cat <<'EOF'
ULTRON — one-command local stack (no sudo, no Docker, no Raspberry Pi)

  ./start.sh              mqtt + backend :8081 + vite :5173 (nothing simulated)
  ./start.sh --feed       also start the mock sensor publisher (stress drill)
  ./start.sh --no-feed    never start it (this is the default)
  ./start.sh --scan       watch the wire for real port sweeps (this is the default)
  ./start.sh --no-scan    do not run the sweep sensor
  ./start.sh --prod       mqtt + backend :8080 serving the prebuilt dist
  ./start.sh --fresh      wipe auth.db first so the QR enrols a new passkey
  ./start.sh --no-qr      skip QR generation
  ./start.sh --help       this text

The sensor simulation is off by default, so the dashboard shows what is really
there rather than a script that is already mid-story. Start a drill from the
dashboard's SIMULATE button, or from a terminal with ./simulate.sh (run
`./simulate.sh --help` for the scenarios).

Ctrl+C stops every child this script started. Logs land in /tmp/ultron-*.log
EOF
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --prod)    MODE="prod" ;;
    --fresh)   FRESH=1 ;;
    --feed)    FEED=1 ;;
    --no-feed) FEED=0 ;;
    --scan)    SCAN=1 ;;
    --no-scan) SCAN=0 ;;
    --no-qr)   QR=0 ;;
    -h|--help) usage ;;
    *) echo "start.sh: unknown flag: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# --- port topology ---------------------------------------------------------
if [ "$MODE" = "prod" ]; then
  HTTP_PORT=8080
else
  HTTP_PORT=8081
fi

# Every loopback spelling a browser can produce has to be listed, for every port
# in play. The WS upgrade and the WebAuthn origin check both compare the Origin
# header against this list with an exact string match, so carrying only
# "localhost" means the page happily loads on 127.0.0.1 or [::1] and then never
# connects — no websocket, no /healthz, a dashboard that looks permanently
# offline. config._validate accepts these literals for http origins.
ORIGINS=""
for _h in "localhost" "127.0.0.1" "[::1]"; do
  for _p in "$HTTP_PORT" 8080 8081 5173; do
    case ",$ORIGINS," in
      *",http://$_h:$_p,"*) ;;
      *) ORIGINS="${ORIGINS:+$ORIGINS,}http://$_h:$_p" ;;
    esac
  done
done
unset _h _p

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
  # A code on disk that is not the grouped 16-byte form is the legacy 4-byte
  # one — thin for something the docs describe as a shared secret, even behind
  # the 5-per-5-minutes limiter. Drop it so it gets regenerated below rather
  # than keep a weak secret just because the file already exists. An explicit
  # ULTRON_DEMO_CODE is an operator override and is left alone.
  if [ "${#DEMO_CODE}" -ne 33 ] || [ "${DEMO_CODE:16:1}" != "-" ]; then
    DEMO_CODE=""
  fi
fi
if [ -z "$DEMO_CODE" ]; then
  # 128 bits, grouped so it stays readable when copied off the banner by hand.
  _code_hex="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n' | tr 'a-f' 'A-F')"
  DEMO_CODE="${_code_hex:0:16}-${_code_hex:16:16}"
  printf '%s' "$DEMO_CODE" > "$DEMO_CODE_FILE"
fi
# Unconditional, and outside the generate branch: the read path used to leave
# the file at whatever mode it already had, so a world-readable access code
# survived every restart. This is a sign-in secret, so it is owner-only.
chmod 600 "$DEMO_CODE_FILE" 2>/dev/null || true

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
  # `stress` reaches RED and PURPLE; `demo` is an honest home-under-watch story
  # that peaks at YELLOW, which is what made a running drill look like nothing.
  start_bg feed "$REPO" "$PY" -u "$DASH/tools/mock_feed.py" --host 127.0.0.1 --port 1883 --script stress
  sleep 1
fi

# ---------------------------------------------------------------------------
# 8a. Port-sweep sensor (real wire, no simulation)
#
#     tcpdump needs CAP_NET_RAW. Rather than failing the whole stack when it is
#     missing, say so once and carry on: a console that refuses to start because
#     a capability is absent is worse than one that admits it cannot see scans.
# ---------------------------------------------------------------------------
if [ "$SCAN" = 1 ]; then
  if command -v tcpdump >/dev/null 2>&1 &&
     { [ "$(id -u)" = 0 ] || getcap "$(command -v tcpdump)" 2>/dev/null | grep -q cap_net_raw; }; then
    start_bg scan "$REPO" "$PY" -u "$DASH/tools/scan_watch.py" \
      --host 127.0.0.1 --port 1883
  else
    echo "[start] scan: tcpdump cannot capture — run: sudo setcap cap_net_raw,cap_net_admin+eip $(command -v tcpdump 2>/dev/null || echo /usr/bin/tcpdump)"
  fi
fi

# ---------------------------------------------------------------------------
# 8b. Alert manager (Pi3b) — the only writer of the evidence vault
#
#     Notification is configured out-of-band so no credential ever lands in git.
#     Copy .notify.example to .notify (gitignored, 0600) or export the
#     ULTRON_SMTP_* / ULTRON_PUSH_* variables; the environment wins over the file.
#
#     Two independent channels: mail, and an optional push relay (ntfy). With
#     neither configured this still starts — the node records every alert and
#     band change and logs "[mail suppressed]" / "[push suppressed]" instead of
#     sending. Notification sits on top of the record, never underneath it: the
#     vault is this node's actual job and it does not depend on a live relay.
# ---------------------------------------------------------------------------
NOTIFY_CONF="$REPO/.notify"

# One KEY=VALUE from .notify. Never fails: a missing file or key yields an empty
# string, so `set -euo pipefail` cannot trip on a first run before mail is set up.
_notify_get() {
  [ -f "$NOTIFY_CONF" ] || return 0
  { grep -E "^[[:space:]]*$1[[:space:]]*=" "$NOTIFY_CONF" 2>/dev/null || true; } \
    | tail -n1 | cut -d= -f2- \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//'
}

# Secrets live in .env, never in .notify and never in git. Source it first so
# the ULTRON_* names below resolve from it; the environment always wins over
# .notify. `set -a` exports everything the file assigns, so child processes see
# it too — without that, alert_manager would start with no password at all and
# Gmail would answer 535, which the node logs and swallows by design.
if [ -f "$REPO/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO/.env"
  set +a
fi

SMTP_HOST="${ULTRON_SMTP_HOST:-$(_notify_get SMTP_HOST)}"
SMTP_PORT="${ULTRON_SMTP_PORT:-$(_notify_get SMTP_PORT)}"
SMTP_USER="${ULTRON_SMTP_USER:-$(_notify_get SMTP_USER)}"
SMTP_PASS="${ULTRON_SMTP_PASS:-$(_notify_get SMTP_PASS)}"
MAIL_FROM="${ULTRON_MAIL_FROM:-$(_notify_get MAIL_FROM)}"
MAIL_TO="${ULTRON_MAIL_TO:-$(_notify_get MAIL_TO)}"
[ -n "$SMTP_PORT" ] || SMTP_PORT=587
[ -n "$MAIL_FROM" ] || MAIL_FROM=ultron@localhost

PUSH_URL="${ULTRON_PUSH_URL:-$(_notify_get PUSH_URL)}"
PUSH_TOPIC="${ULTRON_PUSH_TOPIC:-$(_notify_get PUSH_TOPIC)}"
PUSH_BANDS="${ULTRON_PUSH_BANDS:-$(_notify_get PUSH_BANDS)}"
[ -n "$PUSH_URL" ] || PUSH_URL=https://ntfy.sh
[ -n "$PUSH_BANDS" ] || PUSH_BANDS=RED,PURPLE

# Mail needs a relay AND somewhere to send it. Half-configured is a mistyped
# file, and the honest response is to say so and keep recording.
MAIL_ON=0
if [ -n "$SMTP_HOST" ] && [ -n "$MAIL_TO" ]; then
  MAIL_ON=1
elif [ -n "$SMTP_HOST" ]; then
  echo "[start] alerts: SMTP_HOST is set but MAIL_TO is empty — mail stays suppressed"
fi

# Push needs only a topic; the server has a sane default. No topic, nothing
# dialled, and the appliance never talks to anything off the LAN.
PUSH_ON=0
if [ -n "$PUSH_TOPIC" ]; then
  PUSH_ON=1
fi

_alert_args=(--db "$ULTRON_EVIDENCE_DB" --smtp-port "$SMTP_PORT" --mail-from "$MAIL_FROM")
if [ "$MAIL_ON" = 1 ]; then
  _alert_args+=(--smtp-host "$SMTP_HOST")
  if [ -n "$SMTP_USER" ]; then
    _alert_args+=(--smtp-user "$SMTP_USER" --smtp-pass "$SMTP_PASS")
  fi
  # MAIL_TO may be comma-, semicolon- or space-separated; --mail-to repeats.
  for _to in $(printf '%s' "$MAIL_TO" | tr ',;' '  '); do
    _alert_args+=(--mail-to "$_to")
  done
fi
if [ "$PUSH_ON" = 1 ]; then
  _alert_args+=(--push-url "$PUSH_URL" --push-topic "$PUSH_TOPIC"
                --push-bands "$PUSH_BANDS")
fi

# A rolling digest every two minutes, so the appliance reports in even when
# nothing crosses a band. Mail only -- the vault is unchanged either way.
SUMMARY_EVERY="${ULTRON_SUMMARY_EVERY:-120}"
case "$SUMMARY_EVERY" in (*[!0-9]*|'') SUMMARY_EVERY=0 ;; esac
if [ "$MAIL_ON" = 1 ] && [ "$SUMMARY_EVERY" -gt 0 ]; then
  _alert_args+=(--summary-every "$SUMMARY_EVERY")
fi

# --dry-run silences BOTH channels, so it may only go on when neither is
# configured. Sending it for a push-only setup would silently mute the push.
if [ "$MAIL_ON" = 0 ] && [ "$PUSH_ON" = 0 ]; then
  _alert_args+=(--dry-run)
fi

start_bg alerts "$REPO" "$PY" -u "$REPO/nodes/pi3b/alert_manager.py" "${_alert_args[@]}"

MAIL_DESC="off — vault only (cp .notify.example .notify)"
if [ "$MAIL_ON" = 1 ]; then MAIL_DESC="$SMTP_HOST:$SMTP_PORT -> $MAIL_TO  (on RED / PURPLE, summary every ${SUMMARY_EVERY}s)"; fi
PUSH_DESC="off — set PUSH_TOPIC in .notify"
if [ "$PUSH_ON" = 1 ]; then PUSH_DESC="$PUSH_URL -> $PUSH_TOPIC  ($PUSH_BANDS)"; fi

if [ "$MAIL_ON" = 1 ] || [ "$PUSH_ON" = 1 ]; then
  echo "[start] alerts: recording + notifying — $MAIL_DESC | $PUSH_DESC"
  echo "[start] alerts: if the broker is still holding RED from a previous run,"
  echo "[start] alerts: the first notification goes out immediately. That is correct."
else
  echo "[start] alerts: vault only, no notification (see .notify.example)"
fi

# ---------------------------------------------------------------------------
# 8c. Indicator bridge (cable -> OLED/NeoPixel board)
# ---------------------------------------------------------------------------
# The ESP32-C3 indicator reads newline JSON on a USB serial port. On the real
# rig nodes/pi4/risk_engine.py writes that link; on the demo laptop there is no
# Pi4 cabled to the panel, so this mirrors the broker onto it instead. USB and
# not the board's own radio: the demo AP is 5 GHz and the C3 is 2.4 GHz-only, so
# the radio can never associate.
#
# Started here, and not by hand, because a bridge that is not part of the stack
# is a bridge that is missing exactly when the panel matters -- a restart used to
# leave the board frozen on its last frame while the dashboard carried on.
SERIAL_PORT="${ULTRON_SERIAL_PORT:-/dev/ttyUSB0}"
if [ -e "$SERIAL_PORT" ]; then
  if [ -r "$SERIAL_PORT" ] && [ -w "$SERIAL_PORT" ]; then
    # The repo venv has no pyserial; the system python does.
    start_bg bridge "$REPO" /usr/bin/python3 "$DASH/tools/serial_bridge.py" --port "$SERIAL_PORT"
    echo "[start] bridge: $SERIAL_PORT -> OLED (score, band, open, msg)"
  else
    echo "[start] bridge: $SERIAL_PORT exists but is not read/write — check the dialout/uucp group"
  fi
else
  echo "[start] bridge: no indicator on $SERIAL_PORT (plug the board in, or set ULTRON_SERIAL_PORT)"
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
  API / WS    http://localhost:$HTTP_PORT   (proxied /ws, /auth, /healthz, /debug.html)
  MQTT        127.0.0.1:1883
$( [ "$FEED" = 1 ] && echo "  Mock feed   stress drill, looping forever" || echo "  Mock feed   off — press SIMULATE in the dashboard, or run ./simulate.sh" )
$( [ "$SCAN" = 1 ] && echo "  Sweep sensor  watching the wire for real port scans" || echo "  Sweep sensor  off" )
  Evidence    dev-evidence.db   (written only by the alerts node)
  Mail        $MAIL_DESC
  Push        $PUSH_DESC
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

  Logs  /tmp/ultron-{mqtt,server,vite,feed,alerts}.log
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
