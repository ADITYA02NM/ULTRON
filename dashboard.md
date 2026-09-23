# ULTRON — Premium Dashboard (In-Depth Spec)

> **Non-negotiable:** the dashboard is the face of Black Hat Phase 1 (alert management). *Top notch, no compromise.* Zero dependencies. One file. <100ms. Operator-grade.

**Companion docs:** [`README.md`](README.md) · [`architecture.md`](architecture.md) · [`promt.md`](promt.md) · [`blackhat.md`](blackhat.md)

---

## 1. Design Principles

| # | Principle | Meaning |
|---|-----------|---------|
| 1 | **Operator-first** | Dark UI, monospace data, no marketing chrome. Looks like a NOC wall, not a SaaS landing page. |
| 2 | **Band is the brand** | Entire canvas accents follow GREEN/YELLOW/RED/PURPLE. Color = state, always. |
| 3 | **Zero dependencies** | Single `index.html` (inline CSS+JS). No React, no CDN, no npm, no fonts fetched. Works air-gapped on Pi4:8080. |
| 4 | **Push, don't poll** | MQTT → server → WebSocket → DOM. No `setInterval` polling of the API. |
| 5 | **Latency budget** | Event → painted screen **≤ 100ms** (see architecture.md §4). |
| 6 | **Truthful liveness** | Explicit `LIVE` / `DEGRADED` / `OFFLINE` badge driven by WS state + last message age. Never silently stale. |
| 7 | **Responsive** | 1280px+ desktop primary; usable down to 768px tablet (management WiFi). |

---

## 2. Information Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ HEADER: logo/wordmark │ LIVE badge │ mode chip │ band chip │ clock │
├───────────┬───────────┬───────────┬─────────────────────────────────┤
│ RISK GAUGE│ BAND CARD │ NODE GRID │ DETECTION LAYERS               │
│ (arc+num) │ color+meta│ 4 tiles   │ IDS / Honeypot / Scanners /    │
│           │           │           │ Tripwire — status dots         │
├───────────┴───────────┴───────────┴─────────────────────────────────┤
│ ALERT FEED (filterable)                          [ACK] [EXPORT MD] │
│ severity │ title │ source │ time │ detail expand │ ack state       │
├─────────────────────────────────────┬───────────────────────────────┤
│ RISK HISTORY (24h sparkline/area)   │ RECENT SCANS │ STATS mini     │
│ color-segmented by band             │ tool/host    │ counts        │
├─────────────────────────────────────┴───────────────────────────────┤
│ FOOTER: decay policy │ report path │ uptime │ mqtt endpoint        │
└─────────────────────────────────────────────────────────────────────┘
```

**Priority order (what a mentor sees in 3 seconds):** risk number → band color → red alerts → all nodes green.

---

## 3. Visual System

### 3.1 Color Tokens

```css
:root {
  /* base */
  --bg-0: #070b12;      /* page */
  --bg-1: #0c1320;      /* cards */
  --bg-2: #111a2c;      /* nested */
  --border: #1c2a40;
  --text-hi: #e6edf7;
  --text-mid: #93a4bd;
  --text-low: #5c6f8a;
  --mono: "JetBrains Mono", "SFMono-Regular", ui-monospace, monospace;

  /* bands */
  --green:  #00ff88;
  --yellow: #ffcc00;
  --red:    #ff3b3b;
  --purple: #b14aff;

  /* active band (JS sets on <html data-band=…>) */
  --accent: var(--green);
  --accent-dim: color-mix(in srgb, var(--accent) 18%, transparent);
}
html[data-band="GREEN"]  { --accent: var(--green); }
html[data-band="YELLOW"] { --accent: var(--yellow); }
html[data-band="RED"]    { --accent: var(--red); }
html[data-band="PURPLE"] { --accent: var(--purple); }
```

**Severity colors:** CRITICAL = red · WARNING = yellow · INFO = cyan-ish `#3aa0ff`.

### 3.2 Typography Scale

| Token | Size | Weight | Use |
|-------|------|--------|-----|
| display | 48–64px | 700 | risk score number |
| h2 | 18px | 600 | card titles (uppercase, 0.08em tracking) |
| body | 14px | 400 | alert titles |
| meta | 11–12px | 400 | timestamps, sources |
| micro | 10px | 500 | badges, chips |

### 3.3 Geometry & Spacing

- Radius: cards `10px`, chips `999px`, dots `50%`.
- 8px spacing grid (`--s1: 8px … --s4: 32px`).
- Card: `1px solid var(--border)`, subtle `box-shadow: 0 8px 24px rgba(0,0,0,.35)`.
- Accent glow: `box-shadow: 0 0 24px var(--accent-dim)` on band chrome only (not every card).

### 3.4 Motion

| Element | Motion | Timing |
|---------|--------|--------|
| Risk arc | tween to target | 600ms `cubic-bezier(.2,.8,.2,1)` |
| Band change | chip + border crossfade | 300ms |
| New alert | slide-in from top + flash | 250ms; respect `prefers-reduced-motion` |
| LIVE dot | pulse opacity | 1.6s infinite |
| Sparkline append | instant (data honesty > flourish) | — |

---

## 4. Component Specifications

### 4.1 Header

```
 ULTRON // IOT SECURITY ECOSYSTEM   [● LIVE]  [ULTRON MODE]  [● YELLOW]  12:04:31Z
```

- **LIVE badge:** green pulsing dot + `LIVE` when WS open & last msg <5s; amber `STALE` 5–30s; red `OFFLINE` >30s or socket closed (+ auto-reconnect backoff 1s→15s).
- **Mode chip:** `ULTRON` | `LAB` (from `health`/config topic).
- **Band chip:** full band color, updates from retained `ultron/risk/band`.
- **Clock:** UTC, `HH:MM:SSZ`, ticks 1s (local only — not MQTT).

### 4.2 Risk Gauge (hero)

- SVG arc, 270° sweep, 0→100.
- Track `--bg-2`; progress stroke `--accent`, round cap, soft glow filter.
- Center: score **integer**, `/100` in `--text-low`, band label beneath.
- Sub-line: `Δ +12  ▲` or `−4` from last score (colored), plus `decay −2/10s` microtext.

### 4.3 Band Card

- Large band name + description ("Defense posture", "Normal monitoring", …).
- Escalation **Phase 1** note: `notify only — response is Phase 2`.
- LED strip preview (8 dots) matching ESP32-C3 animation pattern.

### 4.4 Node Grid (4 tiles)

| Tile | Expected heartbeat |
|------|--------------------|
| Pi4 Brain | `ultron/health/pi4` |
| Pi3a Attack | `…/pi3a` |
| Pi3b IDS | `…/pi3b` |
| ESP32 (indicator+tripwire merged) | serial status / GPIO events |

Each tile: name, IP, uptime, mini service pills (mqtt/risk/scan/alert/dashboard), state dot (green up / yellow degraded / red down).

### 4.5 Detection Layers

Four horizontal status rows:

1. **IDS** — Suricata rule count + last alert age  
2. **Honeypot** — Cowrie sessions today  
3. **Scanners** — last run + next in  
4. **Tripwire** — armed state + last edge event  

Each row: dot + label + value. Tripwire `OPEN/CASE` flashes red on edge.

### 4.6 Alert Feed (core of alert management)

**Row:** `[SEV] [title] [source] [age] [▸ detail] [ack]`

- Sort: severity (CRITICAL>WARNING>INFO) then time desc.
- Filters: severity toggles, source select, `unacked only` switch, text search.
- **ACK:** button → publish `ultron/ack/{id}`; optimistic UI + server confirm; acked rows dim with operator initial + time.
- **Detail expand:** raw JSON pretty-printed + risk delta at event time.
- **Virtualization:** render max 200 DOM rows; window the rest (keeps Pi4 CPU honest).
- Empty state: `No alerts — all quiet in the sensor mesh` + armed icons.

### 4.7 Risk History Chart

- 24h, 1-min buckets (server sends last 1440 points on connect + incremental).
- SVG area/line; stroke and fill use band color **per segment** (piecewise coloring).
- Y grid at 30/60/85 band thresholds (dashed, labeled).
- Hover: crosshair + tooltip `{ts, score, band}`.

### 4.8 Recent Scans + Stats

- Last 5 scans: tool badge (`nmap|nuclei|lynis`), target, findings count, duration.
- Stats mini-grid: events/24h, alerts open, ack rate, uptime %.

### 4.9 Footer

- `governance: −2 pts / 10s → baseline 0`
- `reports: ~/ultron/reports/YYYY-MM-DD.md`
- `mqtt: 192.168.100.1:1883` · build hash/version.

---

## 5. Real-Time Data Contract

### 5.1 Transport

- Server opens WS at `/ws` on `:8080`.
- Server subscribes to MQTT allowlist: `ultron/health/#`, `ultron/alert/#`, `ultron/risk/score`, `ultron/risk/band`, `ultron/scan/#`, `ultron/tripwire/#`, plus compressed score history on join.

### 5.2 Message Envelope (client)

```json
{
  "t": "alert|score|band|health|scan|tripwire|history|mode|toast",
  "ts": "2026-09-23T12:04:31.203Z",
  "d": { }
}
```

| `t` | `d` payload (summary) | UI effect |
|-----|----------------------|-----------|
| `score` | `{v: 42, d: +12}` | gauge tween, Δ badge, push history |
| `band` | `{b: "YELLOW", prev: "GREEN"}` | `html[data-band]`, chip, toast on escalation |
| `alert` | `{id, sev, title, src, body, ack:false}` | feed prepend, flash, count++ |
| `health` | `{node, up, services, uptime}` | node tile + layers |
| `scan` | `{tool, host, findings, ms}` | recent scans list |
| `tripwire` | `{node, edge}` | layer flash + toast if `open` |
| `history` | `{points:[[ts,score],…]}` | chart hydrate (once) |
| `toast` | `{sev, msg}` | transient banner (RED/PURPLE) |

### 5.3 Client → Server

- **Ack:** WS send `{"t":"ack","id":…}` → server publishes `ultron/ack/{id}` to MQTT.
- **Export:** HTTP `GET /api/report/today.md` (downloads current view as Markdown).

### 5.4 Reconnect Policy

`backoff = min(15000, 500 * 2^attempt)` + jitter; force `OFFLINE` badge after 3s without open socket; on reopen request `history` snapshot to reconcile missed bands.

---

## 6. Performance Rules

1. **No polling APIs** — WS only (plus one-shot history fetch).
2. **Batch DOM writes** — queue MQTT bursts; flush via `requestAnimationFrame`.
3. **Chart downsample** — client keeps ≤1440 points; server does 1-min aggregates.
4. **Alert cap** — 500 in memory, oldest dropped (full set remains in SQLite).
5. **Zero external assets** — inline SVG icons; system/mono fonts only.
6. **Budget:** main-thread handler p95 < 8ms on Pi4; initial payload < 80KB gzipped.

---

## 7. States & Edge Cases

| State | Behavior |
|-------|----------|
| First load (no WS yet) | skeleton cards, `CONNECTING…` badge |
| MQTT broker down | server sends `t:health` degraded; badge `STALE`; banner `MQTT DEGRADED — buffering` |
| Missing retained risk | gauge `—`, band `UNKNOWN` (gray fallback token) |
| Clock skew | display server `ts` in feed; local clock only in header |
| Huge burst (scan storm) | queue → rAF flush; feed shows `+N events` compaction row |
| `prefers-reduced-motion` | disable tweens/pulses; instant state swaps |
| Very narrow (<768px) | stack hero row; feed full width; hide sparkline labels |

---

## 8. Acceptance Checklist (Phase 1 — demo gate)

- [ ] Opens at `http://192.168.100.1:8080` from operator laptop on `SENTINEL-SECURE`, offline assets only.
- [ ] Retained band/score render on first paint without manual refresh.
- [ ] Injected MQTT event visible in feed **< 100ms** (Chrome performance filmstrip / WS timestamp vs paint).
- [ ] Band change repaints accent theme across gauge, chip, chart threshold glow.
- [ ] RED event → email sent (check mail log) **and** toast shown **and** LED/OLED change.
- [ ] ACK persists across reload (SQLite).
- [ ] Export downloads valid Markdown report.
- [ ] Kill `mosquitto` → badge becomes STALE/OFFLINE; restart → auto-heal to LIVE.
- [ ] Node down simulation → tile red within 30s heartbeat window.
- [ ] Lighthouse/a11y spot-check: contrast AA on text, focus rings on ack buttons, `aria-live="polite"` on feed.
- [ ] Tablet 768–1024px: no horizontal scroll, feed usable.
- [ ] Code: single file ≤ 250KB unminified, no external requests in devtools network panel.

---

## 9. File & Serve Layout (Pi4)

```
~/ultron/dashboard/
├── index.html          # the entire UI (inline CSS/JS)
├── ws.js               # optional split only if it stays zero-dep (prefer inline)
└── assets/             # EMPTY by design — no fetched files

/etc/systemd/system/sentinel-dashboard.service
  ExecStart=/usr/bin/python3 -m ultron.dashboard --port 8080 --root ~/ultron/dashboard
```

Content-Security-Policy (served): `default-src 'self'; connect-src 'self' ws:; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'`.

---

## 10. Future Phases (document, don't build)

| Phase | Dashboard delta |
|-------|-----------------|
| **2** | Response playbooks panel: timeline of auto-actions (firewall/restart), `REVERT` buttons, approval queue optional |
| **3** | Hunt workspace: anomaly cards, attack-path graph, hypothesis runs, model confidence readouts |
| **LAB** | Leaderboard view, challenge cards (Port Scan / Vuln Hunt / WiFi Recon / Honeypot Escape) |

Keep v1 panels stable — future phases **add tabs**, they do not redesign the hero row.

---

## 11. Definition of Done

`dashboard.md` is satisfied only when §8 checklist is green **and** the UI is what a mentor sees first in the Black Hat IoT demo: **risk, band, alerts, nodes — alive in under 100 milliseconds.**
