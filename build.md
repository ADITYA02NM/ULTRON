# ULTRON — Build Plan (2 Tracks)

> Two parallel tracks for Phase 1 (**detection · governance · alert management · premium dashboard**).  
> **Track A** builds the full three-pillar system. **Track B** builds the no-compromise dashboard.  
> They share only the MQTT contract — implement Track B against live topics as Track A brings them up.

**Canonical refs:** [`architecture.md`](architecture.md) · [`dashboard.md`](dashboard.md) · [`blackhat.md`](blackhat.md) · [`promt.md`](promt.md)

---

## 0. Ground rules (both tracks)

| Rule | Value |
|------|--------|
| Mode | **ULTRON only** — continuous, no alternate modes |
| Cloud | **None** — no CDN, npm, SaaS, phone-home |
| MQTT prefix | `ultron/#` only |
| Production net | `192.168.100.0/24` — Pi4 `.1` · Pi3a `.2` · Pi3b `.3` |
| Mgmt net | `192.168.50.0/24` `SENTINEL-SECURE` (AC600 on **Pi4 USB3**) → only `http://192.168.100.1:8080` |
| Evidence | **Pi4 USB3 pendrive** — SQLite WAL + Markdown (SSD = admin-key + SD offload only) |
| Event → pixel | **≤100ms** (demo gate) |
| Out of scope | honeypots, nmap, Nuclei, Lynis, Cowrie, auditd, IPS, active wireless, GPU, cloud, Phase 2/3 |

**Definition of Done (project):** Track A §A9 green **and** Track B §B10 checklist green → rehearsal §I2.

```
Track A  ████████████████████████████████████████►
Track B           ███████████████████████████████►
Integration            ▲ MQTT live              ▲ Demo gate
```

---

# TRACK A — Full system build

> Goal: three Pis + two ESP32s publishing a correct MQTT contract, risk engine running, alerts + reports landing on the Pi4 vault.

---

## A1. Provision OS images (all nodes)

| Step | Node | Action | Done when |
|------|------|--------|-----------|
| A1.1 | Pi4 | Raspberry Pi OS **Lite 64-bit** on SD; hostname `ultron-gov` | boots, SSH key-only |
| A1.2 | Pi3a | Pi OS **Lite 32-bit**; hostname `ultron-det` | boots, SSH key-only |
| A1.3 | Pi3b | Pi OS **Lite 32-bit**; hostname `ultron-alr` | boots, SSH key-only |
| A1.4 | all | disable password SSH; key-only; `PasswordAuthentication no` | password login rejected |
| A1.5 | all | apt update; set NTP (or static clock + later offline cache) | `timedatectl` OK |

**Do not** install honeypot/scanner packages on any node.

---

## A2. Network + firewall (all nodes)

| Step | Action | Done when |
|------|--------|-----------|
| A2.1 | Static eth0: Pi4 `192.168.100.1/24`, Pi3a `.2`, Pi3b `.3` | ping `.1` from each |
| A2.2 | All eth0 → 5-port switch; optional uplink to home router only if span needed | switch LEDs up |
| A2.3 | **nftables deny-first** on every node (allow established, lo; MQTT 1883 only from prod subnet on Pi4; SSH from mgmt later; default drop + log ring) | `nft list ruleset` sane |
| A2.4 | Confirm **no** hostapd/dnsmasq yet | `systemctl status hostapd` inactive |

**Order dependency:** A2 before any service publish test.

---

## A3. Pi4 Governance — MQTT backbone

| Step | Action | Done when |
|------|--------|-----------|
| A3.1 | `apt install mosquitto mosquitto-clients` | unit active |
| A3.2 | Config: listener 1883 localhost+LAN; **no** anonymous if ACLs on; per-client users for det/alr/dash/risk | `mosquitto_sub` auth OK |
| A3.3 | **ACL:** only risk/Pi4 client may `write ultron/risk/#`; others read-only on `risk/#` | wrong client write rejected |
| A3.4 | Retain policy: `ultron/risk/score`, `ultron/risk/band` **retained**; events not retained | `mosquitto_sub -v -t 'ultron/#'` shows retained |
| A3.5 | systemd: `mosquitto` enabled, `After=network-online.target` | reboot survives |

**Contract freeze — publish/subscribe map (do not invent topics):**

| Topic | Who publishes | Who subscribes | Retained |
|-------|---------------|----------------|----------|
| `ultron/suricata/#` | Pi3a | risk, alert, dash | no |
| `ultron/lan/#` | Pi3a | risk, alert, dash | no |
| `ultron/wifi/#` | Pi3a | risk, dash | no |
| `ultron/tripwire/pi3a` | Pi3a | risk, alert, dash | no |
| `ultron/tripwire/pi3b` | Pi3b | risk, alert, dash | no |
| `ultron/risk/score` | **Pi4 only** | all, dash | **yes** |
| `ultron/risk/band` | **Pi4 only** | all, dash | **yes** |
| `ultron/alert/#` | Pi4 / Pi3b | dash, mailer | no |
| `ultron/ack/#` | dash (Track B) | Pi3b | no |
| `ultron/health/#` | all nodes | Pi4, dash | yes |

Alert envelope: `{id, sev, title, src, body, ts, ack:false}`.

---

## A4. Pi3a Detection

| Step | Service | Action | Done when |
|------|---------|--------|-----------|
| A4.1 | `sentinel-lan` | Passive DHCP/ARP **new-device watch** on eth0; publish `ultron/lan/{mac}` with `{mac,ip,vendor,known}` | unknown MAC appears on bus |
| A4.2 | Suricata | **IDS only** (not IPS); ruleset local; eve/log → aggregator → `ultron/suricata/#` | test rule → topic message |
| A4.3 | `sentinel-agg` | Normalize Suricata + LAN into stable JSON for risk | schema matches risk input |
| A4.4 | WiFi | Plug **TL-WN722N**; **passive monitor only** (no inject, no AP); rogue/beacon anomaly → `ultron/wifi/#` | beacon seen, published |
| A4.5 | GPIO | Listen WROOM **GPIO16** path (active-low reed, 50ms debounce); publish **edges** → `ultron/tripwire/pi3a` | open case → one edge event |
| A4.6 | health | Every 10s → `ultron/health/pi3a` `{node,up,services[]}` | dash tile will go green |
| A4.7 | systemd | `suricata`, `sentinel-lan`, `sentinel-agg` restart=always | reboot survives |

**Explicit non-goals on Pi3a:** no Cowrie, no nmap, no Nuclei, no Lynis, no auditd, no active scan.

---

## A5. Pi3b Alert

| Step | Service | Action | Done when |
|------|---------|--------|-----------|
| A5.1 | `sentinel-alert` | Subscribe risk + detections; persist **SQLite alerts**; publish `ultron/alert/#` | alert row + bus message |
| A5.2 | SMTP | On **RED/PURPLE** band or sev≥red: send email (notify-only copy) | RED → mailbox |
| A5.3 | ACK | Subscribe `ultron/ack/#`; update SQLite `ack`/`ack_ts` | ack from curl survives |
| A5.4 | `sentinel-report` | Daily Markdown: band timeline, top sources, LAN joins, open vs acked, uptime | file written |
| A5.5 | Vault sync | Reports + alert DB exports land on **Pi4 pendrive vault** (NFS/rsync/USB share — **not** local Pi3b disk as system of record) | file visible on Pi4 pendrive |
| A5.6 | GPIO | WROOM **GPIO17** → `ultron/tripwire/pi3b` (same debounce/edge rules) | edge event |
| A5.7 | health | 10s → `ultron/health/pi3b` | tile green |
| A5.8 | Constraint | **No** hostapd, **no** AC600, **no** local evidence pendrive on Pi3b | greps clean |

---

## A6. Pi4 Governance — risk engine + evidence + mgmt AP

| Step | Service | Action | Done when |
|------|---------|--------|-----------|
| A6.1 | `sentinel-risk` | Subscribe detection topics; weighted fuse; **only writer** of `ultron/risk/score` + `band` (retained) | score moves on events |
| A6.2 | Weights | Suricata **0.40** · Tripwire **0.30** · WiFi **0.20** · LAN new-device **0.10** | config matches table |
| A6.3 | Math | `clamp(0,100)`; decay **−2 / 10s** toward 0; band hysteresis **+2** | quiet bus → score falls |
| A6.4 | Bands | GREEN 0–29 · YELLOW 30–59 · RED 60–84 · PURPLE 85–100 | boundary tests pass |
| A6.5 | Escalation | Notify-only: log / dash highlight / email+alarm / operator page — **no auto-block** | Phase 1 wording only |
| A6.6 | SQLite | Core schema on **pendrive**: `events, scores, alerts, lan_devices, health` + indexes | WAL live on USB3 |
| A6.7 | Health | `sentinel-heal` + `ultron/health/pi4` every 10s | tile green |
| A6.8 | Mgmt AP | **AC600 on Pi4 USB3**: hostapd SSID `SENTINEL-SECURE` + dnsmasq `192.168.50.0/24`; forward **only** to `:8080` | laptop joins, reaches dashboard URL only |
| A6.9 | Pendrive | Format/mount evidence volume; cron append + nightly backup | path stable across reboot |
| A6.10 | SSD scripts | Portable SSD = admin-key OS image + **SD-offload scripts**; never mounted as live evidence | docs + mount order match |

**Risk input → weight mapping (implementation checklist):**

```
ultron/suricata/*   → 0.40
ultron/tripwire/*   → 0.30
ultron/wifi/*       → 0.20
ultron/lan/*        → 0.10
```

---

## A7. ESP32 firmware

| Step | Board | Firmware rules | Done when |
|------|-------|----------------|-----------|
| A7.1 | **ESP32-C3 SuperMini** | On **Pi4 USB2** serial **115200**; consume JSON @10Hz `{"score","band","nodes","last"}`; drive **SSD1306** (I2C `0x3C`, ≤4Hz) + optional WS2812B ×8; band patterns solid/chase/strobe/pulse; hysteresis 29/30 | OLED shows live score |
| A7.2 | **ESP32-WROOM** | **Radio OFF**; GPIO16 → Pi3a, GPIO17 → Pi3b; active-low reeds; **50ms debounce**; **no buzzer**; power USB2 or 3V3 | case open → MQTT edge ≤100ms path |
| A7.3 | Sanity | WROOM never publishes MQTT itself; C3 is indicator only | architecture greps pass |

---

## A8. Systemd + integration wiring

| Step | Action | Done when |
|------|--------|-----------|
| A8.1 | Order: `network-online` → `mosquitto` → pillar services → dashboard (Track B unit) | one reboot, full stack |
| A8.2 | All units `Restart=always` + 5s delay | kill -9 a service → returns |
| A8.3 | Health publisher 10s on every node | three health topics alive |
| A8.4 | Cross-node: Pi3b report path → Pi4 pendrive; dash WS → localhost MQTT | end-to-end file + bus |

---

## A9. Track A acceptance (system)

- [ ] Three static IPs ping; nftables deny-first on all  
- [ ] MQTT ACL: only Pi4 writes `ultron/risk/#`  
- [ ] Suricata test event → score → band within budget  
- [ ] New LAN device → `ultron/lan/#` → weight 0.10 visible in components  
- [ ] Passive WiFi anomaly path publishes (no TX/inject)  
- [ ] Tripwire open (GPIO16 and GPIO17) → edge topic, debounced  
- [ ] Score decays −2/10s when quiet; hysteresis blocks band flicker  
- [ ] RED/PURPLE → email sent; copy says notify-only / Phase 2 response  
- [ ] Daily report lands on **Pi4 pendrive** (Pi3b has no evidence disk role)  
- [ ] Evidence SQLite WAL on pendrive; SSD only admin-key/offload  
- [ ] `SENTINEL-SECURE` → only `http://192.168.100.1:8080`  
- [ ] C3 OLED tracks score; WROOM radio off; **no buzzer** anywhere  
- [ ] Reboot → all pillar services return without manual steps  

---

# TRACK B — Dashboard build

> Goal: one air-gapped `index.html` + thin Python WS bridge on Pi4:**8080**. Spec = [`dashboard.md`](dashboard.md); acceptance = dashboard.md §8.

**Stack (locked):** single `index.html` (inline CSS + vanilla JS). **No** React, CDN, npm, external fonts, chart libraries. CSP `default-src 'self'; connect-src 'self' ws:; img-src 'self' data:`.

**Serve layout:**

```
/opt/ultron/dashboard/index.html    # the only asset
/opt/ultron/dashboard/server.py     # static + /ws → Mosquitto localhost
/etc/systemd/system/sentinel-dashboard.service   # After=mosquitto
```

---

## B1. Scaffold + server shell

| Step | Action | Done when |
|------|--------|-----------|
| B1.1 | Create `/opt/ultron/dashboard/`; empty `index.html` shell (doctype, CSP meta, root `data-band="GREEN"`) | opens with zero external requests |
| B1.2 | `server.py`: serve static `index.html` on **0.0.0.0:8080**; route **`/ws`** only for WebSocket | `curl :8080` 200 |
| B1.3 | WS ↔ Mosquitto bridge: subscribe allowlist below; push JSON envelope `{t, ts, d}` | message on bus → WS frame |
| B1.4 | `sentinel-dashboard.service`: `After=mosquitto network-online`; restart always | unit green after reboot |
| B1.5 | Optional basic auth on LAN; **never** expose :8080 to WAN | nftables + bind check |

**Subscribe allowlist:**  
`ultron/health/#`, `ultron/alert/#`, `ultron/risk/score`, `ultron/risk/band`, `ultron/lan/#`, `ultron/tripwire/#`, `ultron/suricata/#`, `ultron/wifi/#` + score history on join.

---

## B2. Visual tokens + layout shell

| Step | Action | Done when |
|------|--------|-----------|
| B2.1 | CSS tokens from dashboard.md §3 (`--bg`, `--panel`, `--border`, `--text`, `--muted`, band colors, `--accent`) | dark operator theme |
| B2.2 | `html[data-band=GREEN\|YELLOW\|RED\|PURPLE]` overrides `--accent` | one attribute restyles page |
| B2.3 | Grid regions: header · gauge+band · nodes+layers · feed+chart · stats · footer | matches IA diagram |
| B2.4 | Font: `system-ui` + `ui-monospace` for numbers; risk numeral 72–96px `tabular-nums` | no webfonts |

**Layout map:**

```
┌ Header: ULTRON · LIVE/STALE/OFFLINE · band pill · UTC clock · MODE: ULTRON ┐
├ Risk gauge 0–100          │ Band card + notify-only note + 8-dot preview  ┤
├ Node grid (4 tiles)       │ Detection layers: IDS / LAN / WiFi / tripwire ┤
├ Alert feed + ACK          │ 24h score sparkline                           ┤
├ Stats: events · open · ack rate · uptime · decay note                    ┤
└ Footer: version · MQTT host · evidence path (Pi4 USB3 pendrive) · docs   ┘
```

---

## B3. Header + connection state machine

| Step | Action | Done when |
|------|--------|-----------|
| B3.1 | Connection chip: **LIVE** (green) / **STALE** (>5s, yellow) / **OFFLINE** (red) | honest states |
| B3.2 | WS open → LIVE; no message >5s → STALE; close/error → OFFLINE + retry 1s,2s,5s… | kill Mosquitto → STALE ≤5s |
| B3.3 | Band pill + UTC clock + fixed `MODE: ULTRON` | always visible |

---

## B4. Risk gauge + band card

| Step | Action | Done when |
|------|--------|-----------|
| B4.1 | SVG arc or conic gradient 0–100; center score + `/100`; ticks at 30/60/85 | visual OK at 0 and 100 |
| B4.2 | On `{t:"score"}` tween ≤300ms; no layout shift | smooth updates |
| B4.3 | On `{t:"band"}` set `data-band`; toast if band worsens | accent flips ≤1 frame |
| B4.4 | Band card: name, posture line, **`notify only — response is Phase 2`**, 8-dot LED preview (C3 patterns) | Phase 1 copy only |

---

## B5. Node grid (4 tiles)

| Tile | Heartbeat |
|------|-----------|
| Pi4 Governance | `ultron/health/pi4` |
| Pi3a Detection | `ultron/health/pi3a` |
| Pi3b Alert | `ultron/health/pi3b` |
| ESP32 (indicator + tripwire) | serial / GPIO events |

| Step | Action | Done when |
|------|--------|-----------|
| B5.1 | Tile chrome: name, pillar, IP, uptime, service pills, state dot | static render OK |
| B5.2 | `{t:"health"}` updates dot green/yellow/red | matches Track A health topics |
| B5.3 | Missing heartbeat → yellow then red (fail-visible) | no silent dead node |

---

## B6. Detection layers

| Step | Layer | Source | Done when |
|------|-------|--------|-----------|
| B6.1 | **IDS** | `ultron/suricata/#` | rule count + last alert age |
| B6.2 | **LAN watch** | `ultron/lan/#` | unknown devices today |
| B6.3 | **WiFi** | `ultron/wifi/#` | rogue flag + last beacon anomaly |
| B6.4 | **Tripwire** | `ultron/tripwire/#` | armed + last edge; open edge **flashes red** |

Dot + label + value each; no invented layers.

---

## B7. Alert feed + ACK (alert-management core)

| Step | Action | Done when |
|------|--------|-----------|
| B7.1 | Newest first; severity color bar; fields time/sev/title/src/body | reads clearly |
| B7.2 | `{t:"alert"}` prepend + flash + badge++; **ignore duplicate ids** | bus alerts appear <100ms |
| B7.3 | **ACK** button → publish `ultron/ack/{id}` → badge drops | Pi3b SQLite updates |
| B7.4 | Render cap **200 rows**; empty state `No alerts — all quiet in the sensor mesh` | no DOM blowup |
| B7.5 | ACK offline → queue; flush on reconnect | reconnect test passes |
| B7.6 | **ACK survives page refresh** (server SQLite is source of truth; hydrate on load) | dashboard.md §8 |

---

## B8. History + stats + footer

| Step | Action | Done when |
|------|--------|-----------|
| B8.1 | On join: request/receive history `{t:"history", points:[[ts,score],…]}` | 24h chart on first paint |
| B8.2 | Canvas or light SVG step/sparkline; points colored by band; grid 30/60/85 | no chart library |
| B8.3 | Stats strip: events/24h · alerts open · ack rate · uptime · new devices/24h + `governance: −2 pts / 10s → baseline 0` | numbers live |
| B8.4 | Footer: version, MQTT host, **evidence path on Pi4 USB3 pendrive**, docs links | air-gap truth |

---

## B9. Performance + edge cases

| Step | Rule | Done when |
|------|------|-----------|
| B9.1 | Initial payload **<80KB** gzipped | measured |
| B9.2 | Main-thread handler **p95 <8ms** on Pi4 | measured under event flood |
| B9.3 | Event → paint **<100ms** | demo stopwatch |
| B9.4 | Motion = transform/opacity only; throttle non-critical to rAF; honor `prefers-reduced-motion` | reduced-motion disables animation |
| B9.5 | MQTT down → banner `MQTT DEGRADED`; hold last score **with age** | pull broker cable simulation |
| B9.6 | Duplicate alert id ignored; clock skew prefers server `ts`; empty history = skeleton not error | edge table covered |

---

## B10. Track B acceptance (= dashboard.md §8)

- [ ] Opens **air-gapped** at `http://192.168.100.1:8080` — zero network errors  
- [ ] Event MQTT → pixel **<100ms**  
- [ ] Band change restyles accent everywhere ≤1 frame  
- [ ] RED → email + toast + gauge red  
- [ ] ACK removes badge and **survives refresh** (SQLite)  
- [ ] Kill Mosquitto → header STALE/OFFLINE **within 5s**  
- [ ] 4 node tiles match `ultron/health/#`  
- [ ] Layers: Suricata + LAN + WiFi + tripwire  
- [ ] 24h chart draws from history on first load  
- [ ] Tablet ~1024px usable; no horizontal scroll on desktop  
- [ ] `prefers-reduced-motion` respected  
- [ ] View-source: **one file**, no http(s) subresources  

---

# I. Integration & demo rehearsal

| Step | Track dependency | Action | Gate |
|------|------------------|--------|------|
| I1 | A3 + B1 | Point `server.py` at live Mosquitto; WS envelope matches §5 contract | LIVE chip + first score |
| I2 | A9 + B10 | Full-path rehearsal: inject Suricata **and** tripwire; measure event→pixel; confirm RED email + LED/OLED | **≤100ms** + email + band theme |
| I3 | A6.8 | Join `SENTINEL-SECURE` only; confirm dashboard reachable and WAN blocked | mgmt policy holds |
| I4 | A5.5 + A6.9 | Verify report + WAL on pendrive; pull SSD offload scripts once | evidence path true |
| I5 | always | Mentor 3-second read: risk → band → red alerts → all nodes green | first frame passes |
| I6 | docs | If wiring/topics change: update `architecture.md` + `blackhat.md` + README in **same commit** | sync rules §14 |

---

## Parallelization notes

| Safe to parallelize | Sequential (do not reorder) |
|---------------------|-----------------------------|
| A1–A2 (three images) | A3 before any other MQTT publisher tests |
| A4 and A5 once A3 lives | A6.1 risk engine after detection topics stable |
| B1–B2 while A1–A2 run | B7 ACK end-to-end after A5.3 exists |
| B3–B6 against mock envelopes | B10 acceptance after I1 |
| B8–B9 anytime after B1 | I2 last — both tracks green |

**Mocks:** Track B can develop with a local `mosquitto` + `mosquitto_pub` fixtures for `score/band/alert/health/history` before Pi3s are racked — but **acceptance never runs against mocks**.

---

## Out-of-scope guard (both tracks)

Do **not** open work items for: honeypots, nmap/Nuclei/Lynis/Cowrie/auditd, IPS mode, active wireless, dual operating modes, GPU/cloud/CDN, automated response playbooks, threat hunting UI. Those are Phase 2/3 or deliberately cut — see `blackhat.md`.
