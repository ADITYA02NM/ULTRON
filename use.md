# ULTRON — Dashboard `use.md`

> Complete reference for the **Phase 1 dashboard** (owning node: **Pi4 — GOVERNANCE**, `https://ultron.lan`).
> Written from the actual code (routes, subscriptions, publishes and SQL were grepped).
> Phase 1 is **notify-only**: nothing here blocks, quarantines, or responds. That is Phase 2.

**Stack:** operator UI = **React + TypeScript, built with Vite** (multi-file, `dashboard/web/`). The Pi4 serves only the built static output in `dist/` — it never runs Node/npm and fetches nothing from the internet at runtime. Server = **Python (aiohttp + webauthn==3.0.1) `dashboard/server/`**, serving HTTPS on :443 with offline local CA and WebAuthn passkey owner lock. Debug page = one standalone `dashboard/debug/debug.html` (vanilla JS).

---

## 1. Quick use

```bash
# Build the UI (dev machine only)
cd dashboard/web && npm install && npm run build      # -> dashboard/web/dist

# Run the server (dev)
cd dashboard && pip install -r server/requirements.txt
python -m server.main                                  # serves dist + /ws on :8080

# Open
#   operator : http://<host>:8080/
#   booth TV : http://<host>:8080/?view=booth
#   debug    : http://<host>:8080/debug.html      (only if ULTRON_DEBUG=1 or mgmt subnet+auth)

# Dev demo feed (needs a broker; never run in prod)
python tools/mock_feed.py --host 127.0.0.1 --port 1883 --script demo

# Tests
cd dashboard/web && npm run test        # vitest (web logic)
cd dashboard && python -m pytest        # pytest (server)
```

**Deploy to Pi4**
```bash
# Rsync deploy (includes certs/server.key as 0600; excludes ca/ and ca.key)
make deploy PI=ultron@192.168.50.1

# Install systemd unit
sudo cp systemd/sentinel-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sentinel-dashboard   # start
sudo systemctl stop sentinel-dashboard                                           # stop
```

---

## 2. HTTP endpoints

| Method | Path | Auth / enable | Response | Cache | Used by |
|--------|------|---------------|----------|-------|---------|
| GET | `/` | open (LAN) | React `index.html` (app CSP) | `no-store` | browser |
| GET | `/assets/{file}` | open | hashed JS/CSS/fonts | `public, max-age=31536000, immutable` | browser |
| GET | `/debug.html` | `ULTRON_DEBUG=1`, **or** client in `ULTRON_MGMT_SUBNET` + HTTP Basic auth; else **404** | standalone debug page (hashed CSP) | `no-store` | operator |
| GET | `/healthz` | open | `{ok, mqtt_connected, db_readable, uptime_s, version, ws_clients}` | `no-store` | systemd, debug page |
| GET | `/favicon.ico` | open | `dist/favicon.ico` or `204` | — | browser |
| WS  | `/ws` | **session cookie + Origin** | data stream + ACK in + clock-sync | — | operator, booth, debug |
| POST | `/auth/setup` | enrollment token | begin first-credential registration | — | CLI / setup |
| POST | `/auth/setup/complete` | ceremony cookie | finish first registration + session | — | CLI / setup |
| POST | `/auth/login/begin` | open | begin authentication ceremony | — | browser |
| POST | `/auth/login/complete` | ceremony cookie | finish login + session | — | browser |
| POST | `/auth/reauth/begin` | open | begin re-authentication | — | browser |
| POST | `/auth/reauth/complete` | ceremony cookie | finish re-auth + session refresh | — | browser |
| POST | `/auth/register/begin` | session | begin add-credential ceremony | — | browser |
| POST | `/auth/register/complete` | session + ceremony | finish add credential | — | browser |
| POST | `/auth/logout` | session | revoke session, close WS | — | browser |
| GET | `/auth/status` | open | `{has_owner, authenticated}` | — | browser |
| GET | `/auth/credentials` | session | list credentials | — | browser |
| DELETE | `/auth/credentials/{id}` | session | revoke a credential | — | browser |
| GET | `/{path}` | open | SPA fallback → `index.html` | `no-store` | deep links |

Example `/healthz`:
```json
{"ok":true,"mqtt_connected":true,"db_readable":false,"uptime_s":1.2,"version":"0.4.0-phase1","ws_clients":1}
```
Routes beyond §3's allowed set are justified: `/favicon.ico` (browser default request → 204) and the SPA fallback (`?view=booth` is a query on `/`, but the fallback keeps deep links working).

**CSP.** App pages: `default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'` (the built `index.html` has no inline script/style). `debug.html`: same, but its one inline `<script>` and `<style>` are `sha256`-pinned at startup by `server/csp.py`.

---

## 3. WebSocket `/ws`

Envelope (server → client), `ts` = **MQTT-receive time**, seconds since epoch with **ms precision**:
```json
{ "t": "score|band|alert|health|lan|tripwire|history|toast|event", "ts": 1767000000.123, "d": {} }
```

| `t` | `d` schema | example | from MQTT topic | consumed by |
|-----|-----------|---------|-----------------|-------------|
| `score` | `{v:int}` | `{"v":72}` | `ultron/risk/score` | RiskPanel, History, PipelineStrip |
| `band` | `{b:Band}` | `{"b":"RED"}` | `ultron/risk/band` | App (theme), RiskPanel, IndicatorTwin, Header |
| `alert` | `{id,sev,title,src,body,ts?,ack,ack_ts?}` | `{"id":"a1","sev":"red",…}` | `ultron/alert/#` | AlertFeed, EventFeed |
| `health` | `{node,up?,services?[]}` | `{"node":"pi4","up":9000}` | `ultron/health/#` | NodeTiles, HardwareTwin, StatusStrip |
| `lan` | `{mac,ip?,vendor?,known?,first_seen?,last_seen?}` | `{"mac":"AA:…","known":false}` | `ultron/lan/#` | EventFeed, IoTGraph, StatusStrip |
| `tripwire` | `{node,edge}` | `{"node":"pi3a","edge":"open"}` | `ultron/tripwire/#` | EventFeed, HardwareTwin (lid pop) |
| `history` | `{points:[[ts,score],…]}` | sent once on join | evidence SQLite `scores` | History, RiskPanel |
| `toast` | `{msg,sev}` | `{"msg":"MQTT DEGRADED",…}` | server-generated | DegradedBanner |
| `event` | `{topic,node,kind,sev,summary,src_ip?,dest_ip?,mac?,sig_id?}` | `{"node":"pi3a","kind":"suricata","sev":"red","summary":"ET MALWARE…"}` | `ultron/suricata/#`, `ultron/wifi/#` | EventFeed, IoTGraph |

> **`event` vs `alert`:** `ultron/suricata/#` and `ultron/wifi/#` are surfaced as `t:"event"` (structured passthrough for the unified event feed), **not** `t:"alert"`. Alerts come only from `ultron/alert/#` (owned by Pi3b's alert manager). This separation prevents duplicate alert counts, non-persistent ACKs for bridge-generated IDs, and suricata bursts corrupting ack stats.

**Client → server**
| Message | Example | Server action |
|---------|---------|---------------|
| ACK | `{"ack":"a1"}` | publishes `ultron/ack/a1` (QoS 1, JSON `{id,ts,op:"dashboard"}`). Offline → UI queues, flushes on reconnect. |
| Clock ping | `{"ctl":"ping","c":<client_ms>}` | replies `{"ctl":"pong","c":<client_ms>,"s":<server_ms>}` — **never touches MQTT**, not an envelope type. |

**Connect sequence:** `history` (24h scores from SQLite) → recent alerts replayed as `alert` **with stored `ack`** → a `toast` reflecting broker state → live stream.
**Reconnect:** backoff 1 s → 2 s → 5 s; chip LIVE → STALE (>5 s no frame) → OFFLINE (socket closed).

---

## 4. MQTT

**Subscribed (allowlist — exactly these 8, nothing else):**
`ultron/health/#`, `ultron/alert/#`, `ultron/risk/score`, `ultron/risk/band`, `ultron/lan/#`, `ultron/tripwire/#`, `ultron/suricata/#`, `ultron/wifi/#`.

**Published (the only publish in the whole server):** `ultron/ack/{id}` — QoS 1, not retained.

| Topic | Publisher (owner) | Retained | Dashboard role |
|-------|-------------------|----------|----------------|
| `ultron/risk/score` · `ultron/risk/band` | **Pi4** | yes | subscribe (read) |
| `ultron/alert/#` | Pi4 / Pi3b | no | subscribe |
| `ultron/suricata/#` · `ultron/lan/#` · `ultron/wifi/#` · `ultron/tripwire/#` | Pi3a (tripwire also Pi3b) | no | subscribe |
| `ultron/health/#` | all nodes | yes | subscribe |
| `ultron/ack/#` | **dashboard** → Pi3b | no | **publish only** |

The dashboard **never** writes `ultron/risk/#` (that is Pi4's `sentinel-risk`), and never invents topics.

---

## 5. Data changes (who writes what)

**Frontend store fields ← which message** (`dashboard/web/src/store/store.ts`):

| Message | Store mutation |
|---------|----------------|
| `score` | `score`, `scoreTs`, append `history`, `pipeline.govern` |
| `band` | `band`; `bandBump++` if worse |
| `history` | replace `history`; sync `score` |
| `alert` | prepend `alerts` (dedupe by id, cap 200); `eventCount++`, `ackTotal++`, `openCount`/`ackDone`; append to `events` as `kind:"alert"`; `pipeline.alert` |
| `event` | `eventCount++`; append to `events` (cap 500) with structured fields; suricata→`layers.ids*`, wifi→`layers.wifi*`; `pipeline.detect` |
| `health` | `nodes[node] = {up,lastSeen}`; `pipeline.{govern|detect|alert}` |
| `lan` | `layers.lanToday++`, `eventCount++`, `pipeline.detect` |
| `tripwire` | `layers.tripLast`, `layers.tripSeq++`, `eventCount++`, `pipeline.{detect|alert}` |
| `toast` | `degraded` on/off, `lastToast` |
| (client) `ackLocal` | mark alert acked, `openCount--`, `ackDone++` (optimistic) |
| (pong) | `clock` offset/uncertainty; feeds `latencyLast`/`latencyP95` |

**SQLite reads (read-only, `dashboard/server/db.py`):**
- `SELECT ts, score FROM scores WHERE ts >= ? ORDER BY ts ASC` — 24h history for the chart on join.
- `SELECT id, ts, sev, title, src, body, ack, ack_ts FROM alerts WHERE ts >= ? ORDER BY ts DESC LIMIT ?` — recent alerts + **stored ack** (so ACK survives refresh).
- `SELECT 1` — `db_readable` probe for `/healthz`.

**ACK flow, end to end:** ACK button → WS `{ack:id}` → server `bridge.publish_ack` → **`ultron/ack/{id}`** → Pi3b writes `alerts.ack` / `alerts.ack_ts` → on refresh the server replays that alert with `ack:true`.

**The dashboard never writes:** `ultron/risk/#`, any other MQTT topic, or the evidence DB (opened `mode=ro`).

### 5.1 Operator commands (`lib/commands.ts` — 19 total)

| # | Command | Args | Mode | Description |
|---|---------|------|------|-------------|
| 1 | `/help` | — | client | List commands with args |
| 2 | `/filter` | `<sev:x src:x type:x>` | client | Filter the events panel |
| 3 | `/clear-filter` | — | client | Reset event filters |
| 4 | `/focus` | `<pi4\|pi3a\|pi3b\|c3\|wroom>` | client | Highlight a node in the device map |
| 5 | `/device` | `<ip\|mac>` | client | Open a device card in the IoT graph |
| 6 | `/history` | `<1h\|6h\|24h>` | client | Change the chart range |
| 7 | `/view` | `<operator\|booth>` | client | Switch view |
| 8 | `/latency` | — | client | Print latency stats |
| 9 | `/health` | — | client | Print per-node heartbeat ages |
| 10 | `/mute` | `<minutes>` | client | Mute toasts |
| 11 | `/export` | `alerts` | client | Browser-side CSV of alerts |
| 12 | `/ack` | `<id\|all>` | server | Acknowledge alert(s) — requires authenticated session |
| 13 | `/lock` | — | server | End the session (logout) |
| 14 | `/devices` | — | server | List registered passkeys — requires authenticated session |
| 15 | `/block` | — | Phase 2 (disabled) | Block a device |
| 16 | `/isolate` | — | Phase 2 (disabled) | Isolate a segment |
| 17 | `/quarantine` | — | Phase 2 (disabled) | Quarantine a host |
| 18 | `/restart` | — | Phase 2 (disabled) | Restart a service |
| 19 | `/scan` | — | Phase 2 (disabled) | Scan network |

Modes: **client** = runs in browser, no server; **server** = requires authenticated WS session (rejects with "sign in first" if unauthenticated); **Phase 2 (disabled)** = response action, rejected with "Phase 2" message, chip disabled in UI. The `COMMANDS` array has exactly **19** entries (`lib/commands.ts`).

**Quick Controls** (6 buttons): ACK ALL, UNACKED, FOCUS NODE, BOOTH VIEW, EXPORT CSV, LOCK.

---

## 6. What was built for what

| Thing | Does | Reads | Satisfies | Node |
|-------|------|-------|-----------|------|
| `web/store` | external store + selectors (useSyncExternalStore), rAF-batched | all `t` | perf §6.2, render isolation | Pi4 |
| `web/transport` | WS client, reconnect, ACK queue, clock sync, latency | `/ws` | §7 states, clock skew | Pi4 |
| `RiskPanel` | numeral + ring gauge + failure grey | score/band/conn | §4.2, 6.6 | Pi4 |
| `HardwareTwin` | SVG shelf; health LEDs, cable pulses, tripwire lid pop | health/tripwire/events | §6.1, README §7 beat 3 | all |
| `PipelineStrip` | DETECT→GOVERN→ALERT + bus→screen latency + p95 | pipeline/latency | §6.3, perf gate | all |
| `AlertFeed` | cards, ACK, dedupe, window 200, empty state | alerts | §4.6 alert mgmt | Pi3b |
| `DetectionLayers` | IDS/LAN/WiFi/Tripwire rows; trip flash | alerts/lan/tripwire | §4.5 | Pi3a |
| `IndicatorTwin` | 128×64 OLED canvas + 8 LEDs (band pattern) | score/band/nodes | §4.3, ESP32-C3 mirror | Pi4/ESP |
| `NodeTiles` | 4 tiles, state dot, uptime, service pills | health | §4.4 | all |
| `History` | 24h step ribbon, grid 30/60/85 | history/score | §4.7 | Pi4 |
| `StatsStrip` | events/open/ack%/uptime/new-devices + decay note | derived | §4.8 | Pi4 |
| `Header`/`DegradedBanner` | LIVE/STALE/OFFLINE, band pill, clock; degraded banner | conn/band | §4.1, 6.6 | Pi4 |
| `BoothView` | 1920×1080 TV view (lazy) | same store | §6.7 | Pi4 |
| `server/main` | routes, /ws, /healthz, static, debug gating | — | §3 | Pi4 |
| `server/bridge` | MQTT↔WS allowlist, envelope, fan-out, ack publish | MQTT | §4, §5 | Pi4 |
| `server/db` · `csp` · `clock` · `config` | evidence reads · CSP · ping-pong · env | — | §2, §3 | Pi4 |
| `debug.html` | 6-panel read-only inspector (standalone; palette mirrors `tokens.css`) | `/ws`, `/healthz` | §7 | Pi4 |
| `tools/mock_feed` | dev demo publisher (`--script demo`) | — | §9 rehearsal | dev |

### 6.1 Design system files (design-v2, "Intelligence Brief")

| File | Role |
|---|---|
| `design/DESIGN.md` | mood, references, type roles, 60-30-10, spacing, motion, icon rules, signature element |
| `design/D1-AUDIT.md` · `design/D5-QA.md` | the 23-item generic-AI audit and its item-by-item re-check with evidence |
| `design/before/` · `design/after/` · `design/specimen/` | screenshots (D1 before, D2–D5 after, font specimen) |
| `web/src/styles/tokens.css` | the only place colours, sizes, spacing and durations are defined |
| `web/src/styles/fonts.css` · `web/src/assets/fonts/` | generated `@font-face` + metric-matched fallbacks · subset woff2 (113.2 KB) |
| `web/scripts/build-fonts.py` (`npm run fonts`) | rebuilds the font subsets from the Fontsource devDependencies (needs `fonttools`, `brotli`) |
| `web/scripts/check-tokens.mjs` (`npm run check:tokens`) | fails on raw hex/rgb/px/ms outside tokens; lists the documented exceptions |
| `web/src/components/Icons.tsx` | custom SVG event-kind icons + severity shapes |
| `web/tests/contrast.test.ts` · `web/tests/token-lint.test.ts` | WCAG contrast in all 4 bands · token rule |

**Dev-only routes** (stripped from production builds by `import.meta.env.DEV`): `?design=specimen` shows the font specimen (Schibsted Grotesk vs IBM Plex Sans); `?seed=GREEN|YELLOW|RED|PURPLE` renders the dashboard with static fake data for design review and never opens the WebSocket.

---

## 7. Config / environment variables

| Var | Default | Effect |
|-----|---------|--------|
| `ULTRON_HTTP_HOST` / `ULTRON_HTTP_PORT` | `0.0.0.0` / `8080` | bind address |
| `ULTRON_MQTT_HOST` / `ULTRON_MQTT_PORT` | `127.0.0.1` / `1883` | broker |
| `ULTRON_MQTT_USER` / `ULTRON_MQTT_PASS` | `dash` / `` | broker auth (empty user = anonymous) |
| `ULTRON_EVIDENCE_DB` | `/mnt/pendrive/ultron/ultron.db` | read-only evidence SQLite |
| `ULTRON_DIST` | auto (`dashboard/dist` → `web/dist`) | built app directory |
| `ULTRON_DEBUG` | `0` | `1` enables `/debug.html` globally |
| `ULTRON_MGMT_SUBNET` | `192.168.50.0/24` | subnet allowed to reach `/debug.html` with auth |
| `ULTRON_DEBUG_USER` / `ULTRON_DEBUG_PASS` | `admin` / `` | Basic auth for `/debug.html` |
| `ULTRON_LOG` | `INFO` | log level |
| `ULTRON_TLS_CERT` | *(none)* | path to server certificate (PEM); enables HTTPS when both cert+key are set |
| `ULTRON_TLS_KEY` | *(none)* | path to server private key (PEM) |
| `ULTRON_HTTPS_PORT` | `443` | HTTPS listen port (used only when TLS enabled) |
| `ULTRON_REDIRECT_HTTP` | `1` | `1` = plain HTTP on `ULTRON_HTTP_PORT` returns 301 → HTTPS |
| `ULTRON_AUTH_DB` | `dashboard/auth.db` | auth SQLite (sessions, credentials, audit) |
| `ULTRON_RP_ID` | `localhost` | WebAuthn relying party ID (must be hostname, not IP) |
| `ULTRON_RP_NAME` | `ULTRON` | WebAuthn relying party display name |
| `ULTRON_ORIGINS` | `http://localhost:8080` | comma-separated allowed origins (non-localhost `http://` rejected) |
| `ULTRON_SESSION_TTL` | `3600` | session lifetime in seconds |

**Config guards** — server refuses to start if:
1. `ULTRON_ORIGINS` contains a non-localhost `http://` origin
2. `ULTRON_DEBUG=1` with a non-localhost `ULTRON_RP_ID`
3. `ULTRON_RP_ID` is an IP address (must be a hostname)
4. Only one of `ULTRON_TLS_CERT` / `ULTRON_TLS_KEY` is set (must be both or neither)
5. TLS cert or key file does not exist

---

## 8. Fixed issues

| Issue | Status | Detail |
|-------|--------|--------|
| **Unauthenticated WS ACK** | **closed (CP4)** | WS upgrade now requires a valid session cookie and matching `Origin` header. ACK is accepted only on an authenticated socket. Prior to CP4, any LAN client could send `{"ack":"<id>"}` over WS and acknowledge alerts without authentication. |
| **Fake-alert mapping** | **closed (CP5)** | `ultron/suricata/#` and `ultron/wifi/#` are now surfaced as `t:"event"` (structured passthrough), **not** `t:"alert"`. Alerts come only from `ultron/alert/#` (Pi3b alert manager). Prevents duplicate alert counts, non-persistent ACKs for bridge-generated IDs, and suricata bursts corrupting ack stats. |
| **Logout not closing WS** | **closed (CP6)** | `handle_logout` now calls `session_mgr.close_session_sockets(sid_hash)` to close all WebSockets for the revoked session within 1 s (code 4401). Previously, WS connections could outlive a revoked session until the next heartbeat check. |
| **auth.db WAL mode** | **closed (CP6)** | `auth_db.py` opens with `PRAGMA journal_mode=WAL` for crash resilience and has an explicit `close()` called on shutdown. WAL prevents partial writes to the credential and session tables on unclean process exit. |
| **Rate limiter counting all attempts** | **closed (CP6)** | `_check_rate` counts every auth request (success and failure) — 5 per 5-minute window with exponential backoff. This is intentional: counting only failures would let an attacker with a valid credential rotate it against rate limits. Audit log records `rate_limited` events. |
| **`window.__ultron` store exposure** | **closed (D2)** | `?perf` / `?seed` previously put the full client store (including `setAuth`) on `window.__ultron` in every build. It could not reach live data (the WS upgrade is the boundary), but it let anyone flip the UI past the auth gate. Now the store handle is set only under `import.meta.env.DEV`; production `?perf` exposes a frozen, read-only `metrics()` snapshot (latency last/p95, event count, conn). Verified: `dist/` has no `__ultron.store`. `tests/server/test_ws_refusal.py` covers no cookie, forged/expired/revoked session, wrong/missing Origin, unauthenticated ACK and post-logout ACK (9 tests). |

---

## 9. Known gaps

- **Left out (bus carries no data):** WiFi "last beacon anomaly" detail and Suricata "rule count" are approximated from the alert stream (`src`), since no dedicated topic/field exists. IDS "rule count" shows alert count, not loaded-rule count.
- **CSS modules:** the brief suggested per-component CSS modules; the app uses one `styles/global.css` + `tokens.css` (smaller bundle) — a deliberate deviation.
- **hardware.png vs docs (docs authoritative):** (1) switch port numbering; (2) ESP32-WROOM shown on USB "serial" vs docs GPIO-only/radio-off; (3) pendrive on USB2 hub vs Pi4 USB3; (4) TL-WN722N on Pi4 vs Pi3a; (5) SSD "NAS" vs admin-key/offload; (6) extra USB2 hub (docs: none); (7) fan vs passive heatsink; (8) 3 AC outlets vs one PSU strip; (9) tripwire Pi-side pin labels vs the `ultron/tripwire/pi3a|pi3b` topic contract. The hardware twin follows **architecture.md §3.6**.

Phase 2 (response) and Phase 3 (hunting) are documented in the roadmap only — no code shipped.

---

## 10. HTTPS with local CA (`ultron.lan`)

### 10.1 Generating certificates

Run from the repo root:

```bash
bash tools/make_local_ca.sh
```

This creates:
- `ca/ca.key` — root CA private key (**never goes on the Pi or into git**)
- `ca/ca.crt` — root CA certificate (install on owner devices)
- `certs/server.crt` — server certificate for `ultron.lan` (deploy to Pi)
- `certs/server.key` — server private key (deploy to Pi, mode 0600)

To reissue a server certificate from the existing CA (e.g., nearing expiry):

```bash
bash tools/make_local_ca.sh --reissue
```

### 10.2 Installing the CA certificate on owner devices

After generating, note the SHA-256 fingerprint printed by the script. Verify it matches on each device before trusting.

**Android:**
1. Copy `ca/ca.crt` to the phone (USB, QR, AirDrop).
2. Settings → Security → Encryption & credentials → Install a certificate → **CA certificate**.
3. Select `ca.crt`. Confirm the fingerprint matches.
4. The certificate appears under "User certificates".

**Windows:**
1. Press Win+R → type `certmgr.msc` → Enter.
2. Right-click **Trusted Root Certification Authorities → Certificates** → All Tasks → **Import**.
3. Select `ca/ca.crt`. Finish the wizard.
4. Verify: double-click the imported cert → Details → Thumbprint (SHA-256) must match.

**macOS:**
1. Open **Keychain Access**.
2. Drag `ca/ca.crt` into the **System** keychain (or File → Import Items).
3. Double-click the imported cert → Trust → set to **Always Trust**.
4. Verify the fingerprint in the certificate details.

**Linux (Debian/Ubuntu):**
```bash
sudo cp ca/ca.crt /usr/local/share/ca-certificates/ultron-ca.crt
sudo update-ca-certificates
```

### 10.3 Name resolution

`ultron.lan` must resolve to Pi4's management-plane IP — the wlan1/AC600 address on the `192.168.50.0/24` SENTINEL-SECURE network. On the Pi4, dnsmasq provides this:

```ini
# /etc/dnsmasq.d/ultron.conf
# Replace 192.168.50.1 with Pi4's actual wlan1 IP if different.
address=/ultron.lan/192.168.50.1
```

The HTTPS server must listen on this same address (set `ULTRON_HTTP_HOST` to the wlan1 IP, or leave `0.0.0.0` to bind all interfaces).

Verify from a client on the AP:
```bash
dig @192.168.50.1 ultron.lan   # expect A 192.168.50.1
```

### 10.4 Production config

```bash
# systemd env (in sentinel-dashboard.service)
ULTRON_RP_ID=ultron.lan
ULTRON_ORIGINS=https://ultron.lan
ULTRON_TLS_CERT=/opt/ultron/dashboard/certs/server.crt
ULTRON_TLS_KEY=/opt/ultron/dashboard/certs/server.key
ULTRON_HTTPS_PORT=443
ULTRON_HTTP_PORT=8080
ULTRON_REDIRECT_HTTP=1
```

The server listens on:
- **443 (HTTPS)**: the dashboard (TLS with `server.crt`/`server.key`)
- **8080 (HTTP)**: returns `301` redirect to `https://ultron.lan/`

HSTS header: `Strict-Transport-Security: max-age=31536000` (no `includeSubDomains`).

Cookies: `Secure; HttpOnly; SameSite=Strict`.

CSP tightened in production: `connect-src 'self' wss://ultron.lan` (no bare `ws:` or `wss:` wildcard).

### 10.5 RP ID and credential portability

Passkeys are bound to the **RP ID** (`ultron.lan` in production, `localhost` in dev). Credentials enrolled on `localhost` do **not** work on `ultron.lan` — enrollment must be redone for the production origin.

### 10.6 Real-device smoke test procedure

> **Status: PENDING — operator device test.** Steps (a)–(d) below have not been executed on real hardware. The procedure is validated offline; actual device results will be recorded here after the operator runs the test.

Prerequisites: Pi4 running with HTTPS, owner's laptop and phone on `SENTINEL-SECURE`, CA installed on both.

**(a) Padlock check (laptop):**
Open `https://ultron.lan` — browser shows padlock, no certificate warning.

**(b) Laptop enrollment:**
```bash
# On Pi4 via SSH
python -c "from server.auth_cli import cmd_enroll_token; ..." 
# or: python -m server.auth_cli enroll-token
```
Open the printed URL on the laptop → Windows Hello / Touch ID prompt → register → dashboard loads.

**(c) Phone enrollment:**
Generate a second enrollment token. Open the URL on the phone → fingerprint prompt → dashboard loads.

**(d) Lock + unlock (both devices):**
Click SIGN OUT on each device → lock screen. Click UNLOCK WITH PASSKEY → biometric prompt → dashboard.

**Fallback:** if `ultron.lan` fails WebAuthn on any real device, retry with `ultron.home.arpa` (RFC 8375). Do not proceed past CP6a until both a laptop and a phone can unlock.

### 10.7 Deploy safety (`ca.key` never on Pi)

`ca.key` lives on the admin SSD only. It is used once (or on reissue) to sign server certificates and then stays offline. The `Makefile` `deploy` target enforces this:

```bash
make deploy PI=ultron@192.168.50.1
```

The target:
1. **Aborts** if `ca/` or `ca.key` exists in the repo tree — move them to the admin SSD first.
2. **Excludes** `ca/` and `ca.key` via rsync `--exclude` (but **includes** `certs/server.key`).
3. After rsync, sets `certs/server.key` to mode `0600` owned by the service user on the Pi.

`.gitignore` excludes `ca/` and `*.key` — they cannot be committed accidentally.

### 10.8 Smoke-test runner (`tools/smoke_pi.sh`)

Run on the Pi4 over SSH to bring up just enough for the device test:

```bash
ssh ultron@192.168.50.1
cd /opt/ultron/dashboard
bash tools/smoke_pi.sh
```

The script:
1. Checks that hostapd is running on wlan1 (the SENTINEL-SECURE AP). Fails clearly if not.
2. Finds Pi4's management-plane IP on `192.168.50.0/24`.
3. Verifies `certs/server.crt` and `certs/server.key` exist; aborts if `ca/ca.key` is present.
4. Installs the dnsmasq snippet (`/etc/dnsmasq.d/ultron.conf`) with the detected IP.
5. Prints `dig @127.0.0.1 ultron.lan` to verify DNS.
6. Generates a one-time enrollment token and prints the URL.
7. Starts the HTTPS server on the management IP, port 443, with `ULTRON_RP_ID=ultron.lan`.

**Laptop-only fallback** (test steps (a) and (b) without the Pi):

1. Add a hosts-file entry:
   - Linux/macOS: `sudo sh -c 'echo "127.0.0.1 ultron.lan" >> /etc/hosts'`
   - Windows: add `127.0.0.1 ultron.lan` to `C:\Windows\System32\drivers\etc\hosts`
2. Run the server locally on 443:
   ```bash
   ULTRON_TLS_CERT=certs/server.crt ULTRON_TLS_KEY=certs/server.key \
     ULTRON_RP_ID=ultron.lan ULTRON_ORIGINS=https://ultron.lan \
     ULTRON_HTTPS_PORT=443 ULTRON_REDIRECT_HTTP=0 \
     python -c "from server.main import main; main()"
   ```
3. Open `https://ultron.lan` in the browser (after installing the CA cert).

---

## 11. Recovery Runbook

### 11.1 Lost phone (one passkey remains)

No action needed. The owner still unlocks via the remaining device (laptop). To revoke the lost credential:
1. Sign in on the remaining device.
2. `/devices` → note the credential ID of the lost phone.
3. DELETE `/auth/credentials/{id}` (or via a future admin UI).
4. Re-enroll a replacement device with a new enrollment token.

### 11.2 All passkeys lost

The owner cannot unlock. Recovery requires Pi4 SSH access:

```bash
ssh ultron@192.168.50.1
cd /opt/ultron/dashboard
source venv/bin/activate
python -m server.auth_cli reset-owner     # wipes all credentials + sessions
python -m server.auth_cli enroll-token    # prints a one-time URL
```

Open the URL on the new device to re-enroll. The reset is audited in `auth.db`.

### 11.3 Server certificate expiring

Certificates generated by `tools/make_local_ca.sh` are valid for 825 days. To reissue without replacing the CA:

```bash
# On the admin SSD (where ca.key lives)
bash tools/make_local_ca.sh --reissue
# Deploy new cert to Pi4
scp certs/server.crt certs/server.key ultron@192.168.50.1:/opt/ultron/dashboard/certs/
ssh ultron@192.168.50.1 'chmod 600 /opt/ultron/dashboard/certs/server.key; sudo systemctl restart sentinel-dashboard'
```

No client-side CA reinstall required — the root CA has not changed.

### 11.4 CA compromised

If `ca.key` is exposed, all certificates signed by it must be treated as untrusted:

1. Generate a new CA: `bash tools/make_local_ca.sh` (overwrites `ca/`).
2. Install the new `ca/ca.crt` on all owner devices (§10.2).
3. Deploy the new server cert to Pi4 (§11.3 steps).
4. Restart the dashboard.
5. Re-enroll all passkeys — RP ID has not changed, but a clean enrollment is prudent.

### 11.5 Evidence pendrive swapped or failed

The dashboard opens the evidence DB as **read-only** (`ULTRON_EVIDENCE_DB`). If the pendrive is missing or corrupt:

- `/healthz` reports `"db_readable": false`.
- The dashboard still works — auth, WS, alerts all function. The 24h history chart shows "no data" until the pendrive is restored.
- Replace the pendrive, restore from the daily Pi3b report if needed, and restart the service.

---

## 12. Section E — Final Explanation

### E.1 Files changed (CP6a–CP6c)

| File | Change |
|------|--------|
| `dashboard/server/csp.py` | Added `https_port` parameter to both CSP functions for port-aware `wss://` source |
| `dashboard/server/main.py` | Wired `https_port` through to CSP; TLS server setup with `ssl.SSLContext`; HTTP→HTTPS 301 redirect |
| `dashboard/server/auth.py` | WebAuthn endpoints (setup, login, register, logout); session management; rate limiting |
| `dashboard/server/auth_db.py` | SQLite credential/session/token/audit storage; SHA-256 hashing; WAL mode |
| `dashboard/server/auth_cli.py` | CLI for enrollment tokens and owner reset |
| `dashboard/server/ws_session.py` | WS-to-session tracking; `close_session_sockets` for logout |
| `dashboard/server/config.py` | TLS, auth, and RP configuration from environment variables |
| `Makefile` | Wheelhouse build, deploy (rsync with CA exclusion), deploy-setup |
| `nftables/ultron-pi4.nft` | Deny-first firewall: management 443/8080/53/67/22; production 1883/22 |
| `tools/make_local_ca.sh` | Offline CA + server cert generator (EC P-256, SAN `DNS:ultron.lan`) |
| `tools/smoke_pi.sh` | Pi4 smoke-test runner (hostapd, dnsmasq, certs, enrollment, HTTPS start) |
| `tools/dnsmasq-ultron.conf` | dnsmasq snippet for `ultron.lan` → management-plane IP |
| `systemd/sentinel-dashboard.service` | Hardened unit: `NoNewPrivileges`, `ProtectSystem=strict`, `CAP_NET_BIND_SERVICE` |
| `architecture.md` | §2 firewall, §3.1 service table, §7 security controls, §9 systemd, §10 auth.db schema |
| `dashboard.md` | Stack, §5 transport, §7 states, §8 checklist, §9 layout/CSP |
| `build.md` | B10 checklist, B11 deployment steps |
| `README.md` | Pitch, quick start, wiring, §6 dashboard, §7 demo beat 0, Q&A |
| `promt.md` | §5 network map, §4 quality bar, §8 rule 10 |
| `blackhat.md` | §7.2 firewall, §13 dashboard table, §18 security hardening |
| `use.md` | §1 deploy, §8 fixed issues, §10 HTTPS, §11 recovery, §12 this section |

### E.2 Library versions

| Library | Version | Purpose |
|---------|---------|---------|
| `aiohttp` | 3.10.10 | HTTPS server, static serving, WebSocket |
| `aiomqtt` | 2.3.0 | MQTT bridge (subscribe/publish) |
| `aiosqlite` | 0.20.0 | Async evidence DB reads |
| `webauthn` (`py_webauthn`) | 3.0.1 | WebAuthn/FIDO2 registration and authentication |

All installed via air-gapped wheelhouse (`pip download --platform manylinux2014_aarch64 --python-version 3.11 --only-binary=:all:`).

### E.3 Credential storage

- **Credentials:** public key, sign count, transports, device type, AAGUID, backed-up flag stored in `auth.db` table `credentials`. Private keys never leave the authenticator device.
- **Sessions:** only the SHA-256 hash of the session ID is stored in `auth.db` table `sessions`. The raw session ID exists only in the `Secure; HttpOnly; SameSite=Strict` cookie.
- **Enrollment tokens:** only the SHA-256 hash is stored in `auth.db` table `enrollment_tokens`. The raw token is printed once to the terminal and never logged.
- **CA key:** lives on the admin SSD only. Never deployed to the Pi, never committed to git. `Makefile` aborts if `ca/` or `ca.key` exists in the repo tree.

### E.4 Enrollment flow

1. Operator generates a one-time token via CLI (`python -m server.auth_cli enroll-token`).
2. Token hash stored in `enrollment_tokens`; raw token printed once.
3. Owner opens the setup URL → browser sends token to `POST /auth/setup`.
4. Server validates token hash, creates a WebAuthn registration challenge.
5. Browser prompts biometric (Windows Hello / fingerprint) → sends attestation to `POST /auth/setup/complete`.
6. Server verifies with `py_webauthn`, stores credential, creates session, consumes the token.
7. Dashboard loads. Subsequent devices use `POST /auth/register/begin` + `/complete` (requires existing session).

### E.5 Unlock flow

1. Owner opens `https://ultron.lan` → browser calls `GET /auth/status`.
2. If `has_owner: true, authenticated: false` → login screen shown.
3. Browser calls `POST /auth/login/begin` → server returns challenge + allowed credential IDs.
4. Browser prompts biometric → sends assertion to `POST /auth/login/complete`.
5. Server verifies with `py_webauthn`, creates session (SHA-256 hash stored), sets `Secure; HttpOnly; SameSite=Strict` cookie.
6. Dashboard loads; `/ws` upgrade requires valid session cookie + matching `Origin`.

### E.6 Localhost testing

For development without TLS or a Pi:

```bash
cd dashboard
pip install -r server/requirements.txt
python -m server.main    # HTTP on :8080, RP ID = localhost
```

Open `http://localhost:8080`. WebAuthn works on `localhost` (browsers treat it as a secure context). Enrollment tokens work the same way.

### E.7 Localhost → production differences

| Aspect | Localhost (dev) | Production (`ultron.lan`) |
|--------|----------------|---------------------------|
| Transport | HTTP :8080 | HTTPS :443 + HTTP :8080 → 301 |
| RP ID | `localhost` | `ultron.lan` |
| Origins | `http://localhost:8080` | `https://ultron.lan` |
| Cookies | `HttpOnly; SameSite=Strict` (no `Secure`) | `Secure; HttpOnly; SameSite=Strict` |
| CSP `connect-src` | `'self' ws: wss:` | `'self' wss://ultron.lan` |
| HSTS | not sent | `max-age=31536000` |
| Credentials | bound to `localhost` | bound to `ultron.lan` (must re-enroll) |
| CA cert | not needed | install `ca/ca.crt` on owner devices |
| Debug page | `ULTRON_DEBUG=1` | mgmt subnet + basic auth |
