# ULTRON — System Architecture

> In-depth architecture for a **smart-house** Phase 1: **detection · governance · alert management**.  
> Companion docs: [`dashboard.md`](dashboard.md) · [`promt.md`](promt.md) · [`blackhat.md`](blackhat.md)

---

## 1. System Overview

ULTRON is a **three-pillar, zero-cloud** IoT security ecosystem for the **smart house** — cameras, locks, hubs, sensors, and the edge boxes that talk to them:

| Pillar | Node | Responsibility |
|--------|------|----------------|
| **Governance** | Pi4 8GB `.1` | MQTT bus, risk engine, premium dashboard, health, **pendrive evidence**, SSD admin-key/offload scripts |
| **Detection** | Pi3B+ `.2` | Suricata IDS, passive LAN watch, passive WiFi, tripwire sense |
| **Alert** | Pi3B+ `.3` | Alert manager (SMTP), daily reports → **Pi4 pendrive vault**, tripwire sense |

Plus ESP32-C3 (LED/OLED indicator → Pi4 serial) and ESP32-WROOM (GPIO tripwire, **no WiFi**).

```
Detection sensors ──► MQTT (Pi4) ──► Risk Engine ──┬──► Dashboard ( :8080 )
                                                    ├──► LED / OLED
                                                    └──► Alert Manager ──► Email + Reports
```

**Phase 1 = notify.** Automated response and threat hunting are Phase 2/3 only.

---

## 2. Dual-Network Isolation

| Plane | Subnet | Medium | Purpose |
|-------|--------|--------|---------|
| **Production** | `192.168.100.0/24` | Ethernet switch | Smart-home sensors/hosts under watch, MQTT, dashboard |
| **Management** | `192.168.50.0/24` | WiFi AP `SENTINEL-SECURE` (**Pi4 AC600** USB3) | Operator laptop → **only** Pi4:8080 |

**Firewall sketch (nftables, deny-first):**

```
# production: allow established, lo, SSH from mgmt, Pi4:8080 from mgmt
# Pi4: 1883/tcp MQTT only from 192.168.100.0/24
# Pi4 AC600 (wlan1): WiFi clients forward only to 127.0.0.1:8080 / .1:8080
# default drop; log drops to ring buffer
```

---

## 3. Node Deep-Dives

### 3.1 Pi4 — Governance (`192.168.100.1`)

| Service | Tech | In | Out | Failure mode |
|---------|------|----|-----|--------------|
| `mosquitto` | Mosquitto | TCP 1883 / WS 9001 | — | health restart; dashboard `MQTT DEGRADED` |
| `sentinel-risk` | Python | `ultron/*` | `ultron/risk/score`, `ultron/risk/band` (retained) | hold last score; log decay gaps |
| `sentinel-dashboard` | Python + static `index.html` | WS←MQTT | browser `:8080` | serve last-known + STALE banner |
| `sentinel-heal` | Python + systemd | unit states | restart actions, `ultron/health/pi4` | supervised by systemd |
| `hostapd` + `dnsmasq` | AP on **AC600 (USB3)** | mgmt WiFi | `192.168.50.0/24` → :8080 only | dashboard still reachable on eth0 |
| evidence | cron + SQLite | **pendrive (USB3)** | `reports/`, WAL DB | catch-up once; SSD is admin-key/offload only |
| ssd-offload | scripts | portable SSD | move bulky files off Pi SD cards | keeps SD clean; not the live evidence path |

**USB map (Pi4):** USB **3.0** = AC600 + **evidence pendrive** · USB **2.0** = ESP32-C3 mini (serial 115200).

**SSD (portable admin key):** bootable ULTRON admin OS → any laptop → dashboard as admin. Scripts copy files from Pi SD cards onto SSD when docked so SD cards stay clean. Not mounted as the live evidence volume.

**Datastore:** `~/ultron/ultron.db` on **pendrive (USB3)** — events, scores, lan devices, acks. WAL. Nightly backup. SSD holds admin OS image + offloaded archives.

### 3.2 Pi3a — Detection (`192.168.100.2`)

| Service | Role | Egress |
|---------|------|--------|
| Suricata | signature **IDS** (not IPS) | `ultron/suricata/#` via aggregator |
| `sentinel-lan` | passive DHCP/ARP **new-device watch** | `ultron/lan/#` |
| **TL-WN722N** (USB) | **passive** monitor (rogue AP) | `ultron/wifi/#` |
| GPIO listener | ESP32-WROOM case sense | `ultron/tripwire/pi3a` |

**Why no honeypot / active scanner:** behind home NAT nobody reaches Cowrie; nmap/Nuclei burn CPU for audit theater. Passive sensors only.

**IDS placement:** default = mirror/span of switch (zero inline risk). Inline = Phase 2 consideration only.

### 3.3 Pi3b — Alert (`192.168.100.3`)

| Service | Role | Notes |
|---------|------|-------|
| `sentinel-alert` | consume risk + detections | SQLite alerts; SMTP on RED/PURPLE; ACK API |
| `sentinel-report` | daily Markdown | timeline, top events, LAN joins → **Pi4 pendrive vault** (shared/sync) |
| GPIO listener | ESP32-WROOM case sense | `ultron/tripwire/pi3b` |

**Alert path:** MQTT subscribe → persist → email / surface on dashboard (dashboard itself is served from Pi4).

**No hostapd on Pi3b** — management AP lives on Pi4 with the AC600 (USB3). **No evidence pendrive on Pi3b** — vault is Pi4 USB3.

### 3.4 ESP32-C3 mini — Indicator (Pi4 **USB 2.0**)

```
Pi4 USB2 JSON @10Hz serial ──► ESP32-C3 mini ──┬──► SSD1306 OLED (GPIO/I2C)
                                               └──► WS2812B ×8 (optional, GPIO)
```

Frame: `{"score":42,"band":"YELLOW","nodes":4,"last":"ISO"}` + `\n`.  
Non-blocking NeoPixel loop; band hysteresis at 29/30; OLED ≤4 Hz.

### 3.5 ESP32-WROOM — Tripwire (GPIO → Pi3s; optional USB2 power)

```
Case Pi3a ──GPIO16──► pull-up, LOW = open
Case Pi3b ──GPIO17──►
Power     ◄── USB 2.0 (optional) or Pi3 3V3
```

- **WiFi radio OFF** — cannot be remote-disarmed  
- Debounce 50ms; publish edges not levels  
- Data path is **GPIO only** to Pi3a/Pi3b — not networked  
- **No buzzer** — band feedback lives on Pi4 C3 LED/OLED  

---

### 3.6 Hardware Connections (physical wiring)

Complete neat wiring map — shelf / utility-closet install for a smart house.

```
HOME ROUTER ──► [5-port switch]
                  ├─ eth0 Pi4  .1  GOVERNANCE
                  ├─ eth0 Pi3a .2  DETECTION
                  └─ eth0 Pi3b .3  ALERT

Pi4 (real USB map):
  USB 3.0 ── AC600  → hostapd "SENTINEL-SECURE" (mgmt AP)
  USB 3.0 ── pendrive → evidence SQLite + reports vault
  USB 2.0 ── ESP32-C3 mini → OLED (GPIO/I2C) [+ optional WS2812B]
  (dock)   ── SSD → admin-key OS + SD-offload scripts

Pi3a:
  USB ── TL-WN722N (passive monitor)
  GPIO ◄── ESP32-WROOM GPIO16 (case reed)

Pi3b:
  (no USB storage — reports → Pi4 pendrive vault)
  GPIO ◄── ESP32-WROOM GPIO17 (case reed)

SSD (portable):
  bootable admin OS → laptop → dashboard as admin
  scripts move files off Pi SD cards → SSD (keep SD clean)

ESP32-WROOM (WiFi radio OFF; optional USB2 power):
  GPIO16 → Pi3a · GPIO17 → Pi3b
  active-low · debounce 50ms · data path = GPIO only · no buzzer

POWER: PSU strip → Pi4 5V/3A + Pi3a 5V/2.5A + Pi3b 5V/2.5A ≈ 38W
MGMT:  laptop ─WiFi─► Pi4 AC600 ─► only http://192.168.100.1:8080
```

**Wiring table**

| From | To | Medium | Notes |
|------|----|--------|-------|
| Switch ports 1–3 | Pi4 / Pi3a / Pi3b eth0 | Cat6 | Static `.1` `.2` `.3` on `192.168.100.0/24` |
| **Pi4 USB 3.0** | AC600 | USB3 | WPA2 AP → `192.168.50.0/24` |
| **Pi4 USB 3.0** | pendrive | USB3 | Evidence vault (SQLite + reports) |
| **Pi4 USB 2.0** | ESP32-C3 mini | USB2 | Serial **115200**, JSON @10Hz |
| C3 mini GPIO | SSD1306 | I2C `0x3C` | OLED ≤4 Hz |
| C3 mini GPIO | WS2812B DIN | dupont | Optional strip |
| WROOM GPIO16 | Pi3a GPIO | jumper | Case reed, pull-up, LOW = open |
| WROOM GPIO17 | Pi3b GPIO | jumper | Case reed, pull-up, LOW = open |
| WROOM 3V3/GND or USB2 | power | — | Radio off; no buzzer |
| **Pi3a USB** | TL-WN722N | USB | Monitor mode — passive only |
| Pi3b USB | — | — | No local storage; reports → Pi4 vault |
| SSD (portable) | laptop / Pi dock | USB | Admin-key OS + SD-offload scripts |
| Operator laptop | Pi4 AC600 | WiFi | **Only** Pi4:8080 allowed |
| PSU strip | 3× Pi | DC | Shared strip, ~38 W total |

**ESP32-WROOM pin map**

| Pin | Dir | Target | Logic |
|-----|-----|--------|-------|
| GPIO16 | in | Pi3a case reed | pull-up; LOW = open |
| GPIO17 | in | Pi3b case reed | pull-up; LOW = open |
| USB2 / 3V3 | pwr | Pi or hub | radio off (no buzzer) |
| GND | pwr | common | — |

**ESP32-C3 mini pin map (→ Pi4 USB 2.0)**

| Pin | Target | Protocol |
|-----|--------|----------|
| USB | Pi4 USB **2.0** | 115200, JSON @10Hz |
| I2C GPIO | SSD1306 | I2C |
| optional GPIO | WS2812B | NRZ |
| 5V/GND | USB2 power | mini + OLED |

**Smart-house install notes:** stack three boards on a shelf or in a utility closet next to the home router/switch; keep the OLED/LED indicator where band color is visible; tripwire reeds mount on Pi3a/Pi3b case lids; management AP SSID is `SENTINEL-SECURE` on **Pi4 AC600** (operator phone/laptop only — never IoT devices).

---

## 4. Event Pipeline (End-to-End)

| Step | Budget | Owner |
|------|--------|-------|
| Sensor / IDS emits JSON | 0 | Pi3a / tripwire |
| MQTT publish QoS 1 for alerts | ≤10ms | publisher |
| Risk engine fuse + clamp + band | ≤20ms | Pi4 `sentinel-risk` |
| WS push to browser | ≤50ms | `sentinel-dashboard` |
| Paint | ≤30ms | browser |
| **Total event → pixel** | **≤100ms** | demo gate |

Email path may lag seconds (SMTP); LED serial ≤100ms from score publish.

---

## 5. Governance Model (Risk Engine)

**Inputs & default weights:**

| Source | Weight |
|--------|--------|
| Suricata alert | 0.40 |
| Tripwire edge | 0.30 |
| Passive WiFi anomaly | 0.20 |
| New-device (LAN watch) | 0.10 |

- **Score** = clamp(0, 100, weighted sum of active components)  
- **Decay:** −2 points / 10s toward 0 when quiet  
- **Hysteresis:** band changes require +2 past boundary (anti-flap)  
- **Bands:** GREEN 0–29 · YELLOW 30–59 · RED 60–84 · PURPLE 85–100  
- **Only Pi4 writes** `ultron/risk/#` (MQTT ACL)

**Phase 1 escalation (notify only):**

| Band | Actions |
|------|---------|
| GREEN | log |
| YELLOW | dashboard highlight |
| RED | dashboard alarm + **email** |
| PURPLE | + operator page / LED pulse |

Response actions → Phase 2.

---

## 6. MQTT Topic Contract

| Topic | Publisher | Subscribers | Retained |
|-------|-----------|-------------|----------|
| `ultron/suricata/#` | Pi3a | risk, alert, dash | no |
| `ultron/lan/#` | Pi3a | risk, alert, dash | no |
| `ultron/wifi/#` | Pi3a | risk | no |
| `ultron/tripwire/pi3a` | Pi3a | risk, alert | no |
| `ultron/tripwire/pi3b` | Pi3b | risk, alert | no |
| `ultron/risk/score` | Pi4 | all, dash, ESP | **yes** |
| `ultron/risk/band` | Pi4 | all, dash, ESP | **yes** |
| `ultron/alert/#` | Pi4 / Pi3b | dash, mailer | no |
| `ultron/ack/#` | dash | Pi3b | no |
| `ultron/health/#` | all | Pi4, dash | yes |

Envelope (alerts): `{id, sev, title, src, body, ts, ack:false}`.

---

## 7. Security Architecture

| Control | Implementation |
|---------|----------------|
| Network | dual plane; deny-all nftables |
| MQTT | per-client user/pass; ACL: only Pi4 writes `risk/#` |
| SSH | key-only; password auth off |
| Dashboard | bind LAN; optional basic auth; no WAN |
| Evidence | append-only daily logs; hash in report |
| Updates | offline apt cache / vendored packages at demo |

---

## 8. Deployment Topology & Power

Shelf install in a smart house (see also §3.6 wiring):

```
[PSU strip]──Pi4, Pi3a, Pi3b          ~38W total
[5-port switch]──eth0 ×3 (+ optional uplink to home router span)
[AC600 on Pi4 USB3]──mgmt WiFi SENTINEL-SECURE
[USB2]──ESP32-C3 → Pi4 serial + OLED
[USB3]──pendrive evidence on Pi4 · [USB]──TL-WN722N on Pi3a
[SSD portable]──admin-key OS on laptop · scripts offload Pi SD → SSD
[GPIO]──ESP32-WROOM → Pi3a / Pi3b case reeds (no buzzer)
```

| Node | RAM | ~W | OS |
|------|-----|----|-----|
| Pi4 | 8GB | ~15 | Pi OS Lite 64-bit |
| Pi3a / Pi3b | 1GB | ~5 each | Pi OS Lite 32-bit |
| ESP32s | — | &lt;1 | firmware |

**Total ≈ 38W.** Budget guardrail ~**$290** BOM.

---

## 9. Service Lifecycle (systemd)

Order: `network-online` → `mosquitto` → pillar services → dashboard.

| Unit examples | Node |
|---------------|------|
| `mosquitto`, `sentinel-risk`, `sentinel-dashboard`, `sentinel-heal`, `hostapd`, `dnsmasq` | Pi4 Governance (AC600 USB3) |
| `suricata`, `sentinel-agg`, `sentinel-lan` | Pi3a Detection (TL-WN722N) |
| `sentinel-alert`, `sentinel-report` | Pi3b Alert (→ Pi4 pendrive vault) |

Restart=`always` with 5s delay; health publisher every 10s on `ultron/health/#`.

---

## 10. Data Model (SQLite core)

```sql
events(id, ts, source, type, severity, payload_json);
scores(id, ts, score, band, components_json);
alerts(id, ts, sev, title, src, body, ack, ack_ts);
acks(alert_id, ts, operator);  -- or columns on alerts
lan_devices(id, first_seen, last_seen, mac, ip, vendor, known);
health(node, ts, up, services_json);
```

Indexes: `events(ts)`, `alerts(ack, ts)`, `scores(ts)`.

---

## 11. Phase Roadmap vs Architecture

| Phase | Architectural delta |
|-------|---------------------|
| **1 (now)** | Detect + govern + alert + premium dashboard; LED/OLED |
| **2 Response** | `sentinel-response` on Pi4; nftables zones; reversible playbooks on band crossings; audit table |
| **3 Hunting** | `sentinel-hunt` workers; per-host baselines; correlation graph; hypothesis scheduler |

**Invariant across phases:** dual planes, ESP32 roles, MQTT contract (`ultron/#`), SQLite evidence chain, three-pillar node map.

---

## 12. Failure Modes & Responses

| Failure | Detection | Phase 1 response |
|---------|-----------|------------------|
| Broker down | health + WS fail | dashboard STALE/OFFLINE |
| Risk engine dead | systemd restart; score freeze age | restart; hold last band |
| Detection node down | missing `ultron/health/pi3a` | tile red; score decays only |
| Alert node down | no email on RED | tile red; dashboard still LIVE (Pi4) |
| Disk full | df alert | stop noncritical logs; notify |
| Tripwire stuck open | edge flood | rate-limit + yellow health |

---

## 13. Build Order (dependency graph)

1. Images + static IPs + nftables deny-first  
2. Mosquitto + ACLs + health publisher  
3. **Detection:** Suricata → passive LAN watch → passive WiFi  
4. **Governance:** risk engine → SQLite  
5. **Alert:** alert manager → SMTP → reports  
6. **Dashboard last** (needs all topics) — polish until §8 of `dashboard.md` passes  
7. ESP32 firmware (C3 serial, WROOM GPIO)  
8. Full-path demo rehearsal ≤100ms + RED email  

---

## 14. Document Sync Rules

| Change | Update |
|--------|--------|
| Node/services/topics | `architecture.md` + `blackhat.md` |
| Hardware wiring / pins | `architecture.md` §3.6 + `README.md` Hardware connections |
| Dashboard UX/perf | `dashboard.md` + `build.md` Track B |
| Build steps / order | `build.md` (+ `architecture.md` §13 if dependency graph changes) |
| AI assignment / quality bar | `promt.md` |
| Pitch / BOM / roadmap | `README.md` |

Same commit when possible. `ULTRON(SEN3)/` remains a frozen gitignored backup — never edit.
