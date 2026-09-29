# ULTRON — Premium Dashboard Spec

> **Non-negotiable:** The dashboard is the face of Black Hat Phase 1 **alert management**. *Top notch, no compromise.* Zero dependencies. One file. &lt;100ms. Operator-grade.

**Stack:** operator UI is a **React + TypeScript app built with Vite** (multi-file, `dashboard/web/`). Node/npm/Vite are used **only on the dev machine at build time**; Pi4 serves the built static output in `dist/` and fetches nothing at runtime (no CDN, no web fonts — everything same-origin/air-gapped). Runtime deps are React + ReactDOM only; charts/gauges/the hardware twin are hand-built SVG/canvas. Server = **Python (aiohttp)** with `webauthn==3.0.1` for passkey auth. A single standalone `debug/debug.html` (vanilla JS) is the read-only inspector. Served by Pi4 on **`https://ultron.lan`** (:443, TLS with offline local CA); real-time via WebSocket bridged from Mosquitto. There is also a **booth view** (`?view=booth`) for a 1920×1080 TV — a view, not a mode. Full reference: [`use.md`](use.md).

---

## 1. Design Principles

| # | Principle | Meaning |
|---|-----------|---------|
| 1 | **3-second mentor read** | Risk number → band color → red alerts → all nodes green |
| 2 | **Band is the theme** | Entire accent follows `html[data-band]` |
| 3 | **Notify-first copy** | Phase 1 never claims auto-block; response is Phase 2 |
| 4 | **Fail-visible** | LIVE / STALE / OFFLINE always honest |
| 5 | **Zero deps** | Air-gapped on Pi4 |
| 6 | **Ack is state** | Acknowledgements persist in SQLite |
| 7 | **Mobile-OK** | Usable on operator tablet at demo table |

---

## 2. Information Architecture

```
┌ Header ─────────────────────────────────────────────┐
│ ULTRON · LIVE · band chip · UTC clock · mode ULTRON │
├──────────────┬──────────────────────────────────────┤
│ Risk gauge   │ Band card + escalation note          │
│ 0–100        │ notify only — response is Phase 2    │
├──────────────┼──────────────────────────────────────┤
│ Node grid    │ Detection layers (IDS / LAN / …)      │
│ 4 tiles      │                                      │
├──────────────┴──────────────────────────────────────┤
│ Alert feed (ack)          │ 24h score sparkline     │
├───────────────────────────┴─────────────────────────┤
│ LAN joins · events/24h · ack rate · uptime        │
├ Footer: build · MQTT · evidence ────────────────────┤
```

**Priority order:** risk number → band color → red alerts → all nodes green.

---

## 3. Visual System

Direction: **Intelligence Brief** — an editorial security briefing: warm off-black, serif gravity, one restrained signal colour. Full rationale, references and the signature element are in [`design/DESIGN.md`](design/DESIGN.md); this section is the implementation contract.

### Tokens

All values live in `web/src/styles/tokens.css` and nowhere else (enforced by `npm run check:tokens` and `tests/token-lint.test.ts`: no raw hex, rgb(), px or ms outside tokens, bar 0/1/2px, the OLED canvas, SVG viewBox units and `@media` breakpoints). Colours are sRGB hex in `:root`, overridden by `oklch()` under `@supports`. Canvas code reads tokens through `src/lib/cssVars.ts` (cached per band).

| Group | Tokens |
|---|---|
| Surfaces (60%) | `--bg` #100e0c · `--panel` #1a1714 · `--panel-2` #14120f |
| Structure (30%) | `--text` #ddd4c8 · `--muted` #9a8e80 · `--muted-2` #6e6050 · `--border` #2a2420 · `--border-2` #352e28 |
| Signal (10%) | `--accent` / `--accent-weak` / `--accent-line`, switched by `html[data-band]` |
| Band ramps | `--{green,yellow,red,purple}` + `-tint` / `-soft` / `-strong` |
| Spacing | `--space-1..7` = 4 · 8 · 12 · 16 · 24 · 32 · 40px (8px grid, 4px half-step) |
| Type sizes | `--fs-2xs..4xl` = 8–22px, `--fs-display` 64px, booth `--fs-5xl..8xl`, `--fs-booth-*` |
| Shape | `--radius` 3px · `--radius-pill` · `--stroke` 1.5 · hairline = 1px |
| Motion | `--dur` 200ms · `--dur-enter` 180ms · `--dur-sweep` 400ms · `--dur-flash` 800ms · `--dur-pulse` 1.5s · `--ease` |

Contrast is tested, not assumed: `tests/contrast.test.ts` checks body and `--muted` text ≥ 4.5:1, UI/large text ≥ 3:1, and every band accent on the panel and pill text on the accent.

### Type

| Role | Font | Use |
|---|---|---|
| display | Newsreader 700, `--fs-display` | risk numeral (true tabular figures) |
| title | Newsreader 400/700 | wordmark, band name, Risk panel title |
| posture | Newsreader italic 400 | posture line, empty states, lock-screen subhead |
| body / label | Schibsted Grotesk 400–700 | UI text; uppercase only for panel labels and chips |
| data | JetBrains Mono 400–700, `tabular-nums slashed-zero` | every number, time, IP, MAC, command |

Fonts are self-hosted subsets in `web/src/assets/fonts/` (113.2 KB woff2 total, same-origin), built by `npm run fonts`, with metric-matched fallbacks so swapping in causes no layout shift.

### Motion

Motion only signals state change: new-row entry (`--dur-enter`), one header sweep on escalation or reconnect, the band ring easing to a new score, LED patterns that mirror the real WS2812B strip, and the tripwire lid. `prefers-reduced-motion` stops all of it (verified: no running animations, LEDs solid).

### Visual language

- **Hierarchy:** the Risk panel is the only hero (accent top border, tint gradient, serif numeral); the other five panels share one quiet treatment.
- **Severity:** never colour alone — filled shape (circle → triangle → square → diamond) plus bar width; event kinds use a stroked custom SVG icon set (`src/components/Icons.tsx`, no icon library, no emoji).
- **Hardware twin:** inline-SVG line drawing of the real shelf (architecture.md §3.6). Node state is shape + word (filled / half / hollow ring); dead node → `NO HEARTBEAT · Ns` + dashed cable; tripwire → that Pi's lid swings open red. The lock screen reuses it in an idle state with no live status.
- **No gimmicks:** no fake terminals, hex rain, world maps or fake metrics — live data or a clearly-marked empty state only.

## 4. Component Specifications

### 4.1 Header

- Left: wordmark **ULTRON**
- Center: connection chip — `LIVE` (green) / `STALE` (&gt;5s, yellow) / `OFFLINE` (red)
- Right: band pill, clock, `MODE: ULTRON`

### 4.2 Risk Gauge

- SVG arc or conic gradient 0–100
- Center: score + `/100`
- Tick marks at 30 / 60 / 85 band edges
- Animate value changes ≤300ms; no layout shift

### 4.3 Band Card

- Band name + short posture line
- Note: `notify only — response is Phase 2`
- 8-dot LED preview matching ESP32-C3 pattern

### 4.4 Node Grid (4 tiles)

| Tile | Heartbeat |
|------|-----------|
| Pi4 Governance | `ultron/health/pi4` |
| Pi3a Detection | `ultron/health/pi3a` |
| Pi3b Alert | `ultron/health/pi3b` |
| ESP32 (indicator+tripwire) | serial / GPIO events |

Each tile: name, pillar, IP, uptime, service pills, state dot (green/yellow/red).

### 4.5 Detection Layers

1. **IDS** — Suricata rule count + last alert age  
2. **LAN watch** — unknown devices seen today  
3. **WiFi** — rogue AP flag + last beacon anomaly  
4. **Tripwire** — armed + last edge  

Dot + label + value. Tripwire open flashes red on edge.

### 4.6 Alert Feed (core of alert management)

- Newest first; severity color bar
- Fields: time, sev, title, source, body
- **Ack** button → `ultron/ack/{id}` → persists; badge count drops
- Cap render at **200 rows** (window the rest)
- Empty: `No alerts — all quiet in the sensor mesh`

### 4.7 History

- 24h sparkline / step chart of score
- Points colored by band at sample time
- y grid at 30/60/85

### 4.8 Stats strip

- events/24h · alerts open · ack rate · uptime % · new devices/24h  
- Risk decay note: `governance: −2 pts / 10s → baseline 0`

### 4.9 Footer

- version, MQTT host, evidence path (Pi4 USB3 pendrive), link to docs

---

## 5. Real-Time Data Contract

Server (Pi4) subscribes allowlist:  
`ultron/health/#`, `ultron/alert/#`, `ultron/risk/score`, `ultron/risk/band`, `ultron/lan/#`, `ultron/tripwire/#`, `ultron/suricata/#`, `ultron/wifi/#` + score history on join.

WS envelope:

```json
{
  "t": "alert|score|band|health|lan|tripwire|history|toast|event",
  "ts": 1767000000,
  "d": {}
}
```

| `t` | `d` payload | UI effect |
|-----|-------------|-----------|
| `score` | `{v:42}` | gauge tween |
| `band` | `{b:"YELLOW"}` | `data-band` + toast if worse |
| `alert` | `{id,sev,title,src,body,ack:false}` | prepend, flash, count++ |
| `health` | `{node,up,services[]}` | tile state |
| `lan` | `{mac,ip,vendor,known,first_seen?,last_seen?}` | LAN watch layer, IoT graph |
| `tripwire` | `{node,edge}` | layer flash |
| `history` | `{points:[[ts,score],…]}` | chart on connect |
| `toast` | `{msg,sev}` | transient banner |
| `event` | `{topic,node,kind:"suricata"\|"wifi",sev,summary,src_ip?,dest_ip?,mac?,sig_id?}` | event feed row (no alert count change) |

`lan` optional fields: `ip`, `vendor`, `known`, `first_seen`, `last_seen` — all optional, present when the bridge can resolve them.

> **`event` vs `alert`:** `ultron/suricata/#` and `ultron/wifi/#` map to `t:"event"` (passthrough for the event feed), **not** `t:"alert"`. Alerts come only from `ultron/alert/#` (owned by Pi3b's alert manager). This prevents duplicate alert counts, non-persistent ACKs for bridge-generated IDs, and suricata bursts corrupting stats.

**Transport-level control frames (not envelope data, never MQTT):**

| Direction | Frame | Purpose |
|-----------|-------|---------|
| client → server | `{"ctl":"ping","c":<client_ms>}` | clock-sync request |
| server → client | `{"ctl":"pong","c":<client_ms>,"s":<server_ms>}` | clock-sync reply |
| client → server | `{"ack":"<alert_id>"}` | acknowledge an alert |

The browser estimates its offset to the server clock so `bus → screen` latency is honest. Envelope `ts` is stamped at MQTT-receive time, seconds since epoch with ms precision.

---

## 6. Performance Rules

1. Initial JS + CSS **≤150KB** gzipped (report per-chunk sizes; lazy-load booth). Current build ≈ **58KB gz** (index 55 + css 3)  
2. Main-thread handler **p95 &lt;8ms** on Pi4  
3. Event → paint **&lt;100ms** (demo gate)  
4. No layout thrash — transform/opacity only for motion  
5. Chart: canvas or lightweight SVG; no chart library  
6. Throttle non-critical renders to rAF  

---

## 7. States & Edge Cases

| State | Behavior |
|-------|----------|
| **Locked (no owner)** | Setup screen — requires one-time enrollment token to register first passkey |
| **Locked (has owner)** | Login screen — "UNLOCK WITH PASSKEY" → biometric prompt |
| **Authenticated** | Dashboard visible; session cookie active; WS requires valid session |
| WS connect fail | Retry 1s,2s,5s… header `STALE`/`OFFLINE` |
| MQTT down | Banner `MQTT DEGRADED`; last score held with age |
| Score boundary 29/30 | Hysteresis 1 sample — no flicker |
| Duplicate alert id | Ignore |
| ACK offline | Queue; flush on reconnect |
| Empty history | Skeleton, not error |
| Clock skew | Use server `ts` when present |
| Session expired | Redirected to login screen; WS closed |
| Logout | Session revoked; WS closed within 1s |

---

## 8. Acceptance Checklist (Phase 1 — demo gate)

- [ ] Opens air-gapped at `https://ultron.lan` with valid padlock, zero network errors  
- [ ] **Owner passkey enrollment** works on laptop (Windows Hello) and phone (fingerprint)  
- [ ] **Unlock with passkey** works on both devices after logout  
- [ ] **Foreign device denied** — unregistered credential rejected, audit logged  
- [ ] Event MQTT → pixel **&lt;100ms** (measure in demo)  
- [ ] Band change restyles accent everywhere ≤1 frame  
- [ ] RED event → email sent + toast + gauge red  
- [ ] ACK removes badge and survives refresh (SQLite)  
- [ ] Kill Mosquitto → header STALE/OFFLINE within 5s  
- [ ] 4 node tiles match `ultron/health/#`  
- [ ] Detection layers show Suricata + LAN watch + WiFi + tripwire  
- [ ] 24h chart draws from history on first load  
- [ ] Tablet 1024px usable; no horizontal scroll on desktop  
- [ ] `prefers-reduced-motion` disables animations  
- [ ] **Same-origin only** — no external subresources in `dist/` or `debug.html`; network tab shows only same-origin requests + 1 WebSocket  
- [ ] Logout closes WS ≤1s; session idle expiry works  
- [ ] HTTP→HTTPS redirect works; HSTS header present  

---

## 9. File & Serve Layout (Pi4)

Repo layout (built on the dev machine, deployed via `make deploy`):
```
dashboard/web/                      # React + TS source (Vite)  -> dashboard/web/dist
dashboard/server/                   # aiohttp app: main, bridge, clock, db, csp, config, auth, auth_db, auth_cli
dashboard/debug/debug.html          # standalone read-only inspector
dashboard/tools/mock_feed.py        # dev-only demo publisher
tools/make_local_ca.sh              # offline CA + server cert generator
tools/smoke_pi.sh                   # Pi4 smoke test runner
nftables/ultron-pi4.nft             # Pi4 firewall ruleset
systemd/sentinel-dashboard.service  # After=mosquitto network-online; hardened
Makefile                            # wheelhouse, deploy, deploy-setup
```
Deployed on Pi4:
```
/opt/ultron/dashboard/dist/         # vite build output
/opt/ultron/dashboard/server/       # python app
/opt/ultron/dashboard/certs/        # server.crt + server.key (0600)
/opt/ultron/dashboard/venv/         # Python venv (air-gapped wheelhouse install)
/opt/ultron/dashboard/debug/debug.html
/var/lib/ultron/auth.db             # auth database (0600, owned by ultron)
```

- HTTPS :443 → static `dist/` (`/`, `/assets/*`) + `/healthz` + `/auth/*` + `/ws`
- HTTP :8080 → 301 redirect to `https://ultron.lan/`
- `/ws` → JSON bridge to Mosquitto (localhost) + ACK + clock-sync; **requires session cookie + Origin**
- `/debug.html` off by default (`ULTRON_DEBUG=1` or mgmt subnet + basic auth)

**CSP (production):** `default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' wss://ultron.lan; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'`. `debug.html` uses the same directives with its inline `<script>`/`<style>` sha256-pinned.

---

## 10. Future Phases (document, don't build)

| Phase | Dashboard delta |
|-------|-----------------|
| **2 Response** | Playbook cards, quarantine list, “last action” audit trail |
| **3 Hunting** | Hypothesis queue, baseline anomaly heat, attack-path graph |

---

## 11. Definition of Done

`dashboard.md` is satisfied only when **§8 checklist is green** and a mentor’s first frame is: **risk, band, alerts, nodes — alive in under 100 milliseconds.**
