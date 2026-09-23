# ULTRON — System Architecture

> In-depth architecture for a **smart-house** Phase 1: **detection · governance · alert management**.  
> Companion docs: [`dashboard.md`](dashboard.md) · [`promt.md`](promt.md) · [`blackhat.md`](blackhat.md)

---

## 1. System Overview

ULTRON is a **three-pillar, zero-cloud** IoT security ecosystem for the **smart house** — cameras, locks, hubs, sensors, and the edge boxes that talk to them:

| Pillar | Node | Responsibility |
|--------|------|----------------|
| **Governance** | Pi4 8GB `.1` | MQTT bus, risk engine, scanners, premium dashboard, health, evidence |
| **Detection** | Pi3B+ `.2` | Suricata IDS, Cowrie, canaries, lure, passive WiFi, tripwire sense |
| **Alert** | Pi3B+ `.3` | Alert manager (SMTP), daily reports, management AP |

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
| **Management** | `192.168.50.0/24` | WiFi AP `SENTINEL-SECURE` (Pi3b AC600) | Operator laptop → **only** Pi4:8080 |

**Firewall sketch (nftables, deny-first):**

```
# production: allow established, lo, SSH from mgmt, Pi4:8080 from mgmt
# Pi4: 1883/tcp MQTT only from 192.168.100.0/24
# Pi3b WiFi clients: forward only to 192.168.100.1:8080
# default drop; log drops to ring buffer
```

---

## 3. Node Deep-Dives

### 3.1 Pi4 — Governance (`192.168.100.1`)

| Service | Tech | In | Out | Failure mode |
|---------|------|----|-----|--------------|
| `mosquitto` | Mosquitto | TCP 1883 / WS 9001 | — | health restart; dashboard `MQTT DEGRADED` |
| `sentinel-risk` | Python | `ultron/*` | `ultron/risk/score`, `ultron/risk/band` (retained) | hold last score; log decay gaps |
| `sentinel-scan` | Python + nmap/Nuclei/Lynis | timer 15m | `ultron/scan/#`, SQLite | retry next cycle |
| `sentinel-dashboard` | Python + static `index.html` | WS←MQTT | browser `:8080` | serve last-known + STALE banner |
| `sentinel-heal` | Python + systemd | unit states | restart actions, `ultron/health/pi4` | supervised by systemd |
| evidence | cron + SQLite | DB | `reports/`, optional pendrive | catch-up once |

**Datastore:** `~/ultron/ultron.db` — events, scores, scans, acks. WAL. Nightly backup.

### 3.2 Pi3a — Detection (`192.168.100.2`)

| Service | Role | Egress |
|---------|------|--------|
| Suricata | signature **IDS** (not IPS) | `ultron/suricata/#` via aggregator |
| Cowrie | SSH/Telnet honeypot 22/23 | `ultron/cowrie/#` |
| auditd + canary bridge | planted file access | `ultron/canary/#` |
| Web lure | decoy login POST log | `ultron/lure/#` |
| TL-WN722N | **passive** monitor (rogue AP) | `ultron/wifi/#` |
| GPIO listener | case sense | `ultron/tripwire/pi3a` |

**Deception rules:** realistic banners; scripted sessions; no shell escapes; logs rotated + mirrored to Pi4 evidence.

**IDS placement:** default = mirror/span of switch (zero inline risk). Inline = Phase 2 consideration only.

### 3.3 Pi3b — Alert (`192.168.100.3`)

| Service | Role | Notes |
|---------|------|-------|
| `sentinel-alert` | consume risk + detections | SQLite alerts; SMTP on RED/PURPLE; ACK API |
| `sentinel-report` | daily Markdown | timeline, top events, scans |
| hostapd | `SENTINEL-SECURE` AP | WPA2, management plane only |
| dnsmasq | DHCP + DNS | static lease for operator laptop |
| GPIO listener | case sense | `ultron/tripwire/pi3b` if wired here |

**Alert path:** MQTT subscribe → persist → email / surface on dashboard (dashboard itself is served from Pi4).

### 3.4 ESP32-C3 — Indicator

```
Pi4 JSON @10Hz USB serial ──► ESP32-C3 ──┬──► WS2812B ×8
                                         └──► SSD1306 128×64
```

Frame: `{"score":42,"band":"YELLOW","nodes":4,"last":"ISO"}` + `\n`.  
Non-blocking NeoPixel loop; band hysteresis at 29/30; OLED ≤4 Hz.

### 3.5 ESP32-WROOM — Tripwire

```
Case Pi3a ──GPIO16──► pull-up, LOW = open
Case Pi3b ──GPIO17──►
Buzzer    ◄──GPIO4── band pattern
```

- **No WiFi** — cannot be remote-disarmed  
- Debounce 50ms; publish edges not levels  

---

### 3.6 Hardware Connections (physical wiring)

Complete neat wiring map — shelf / utility-closet install for a smart house.

```
HOME ROUTER ──► [5-port switch]
                  ├─ eth0 Pi4  .1  GOVERNANCE
                  ├─ eth0 Pi3a .2  DETECTION
                  └─ eth0 Pi3b .3  ALERT

Pi4  ──USB──► ESP32-C3 ──┬── WS2812B×8 (DIN=GPIO2)
                         └── SSD1306 I2C (SDA/SCL)
     optional ──USB──► evidence pendrive / SSD

Pi3a ──USB──► TL-WN722N (passive monitor)
     GPIO26 ◄──jumper── ESP32-WROOM GPIO16 (case reed)

Pi3b ──USB──► AC600 hostapd "SENTINEL-SECURE" (mgmt AP)
     GPIO26 ◄──jumper── ESP32-WROOM GPIO17 (case reed)

ESP32-WROOM island (WiFi radio OFF):
  GPIO16 → Pi3a case · GPIO17 → Pi3b case · GPIO4 → buzzer+
  3V3/GND from Pi3a header · active-low · debounce 50ms

POWER: PSU strip → Pi4 5V/3A + Pi3a 5V/2.5A + Pi3b 5V/2.5A ≈ 38W
MGMT:  laptop ─WiFi─► Pi3b AP ─► only http://192.168.100.1:8080
```

**Wiring table**

| From | To | Medium | Notes |
|------|----|--------|-------|
| Switch ports 1–3 | Pi4 / Pi3a / Pi3b eth0 | Cat6 | Static `.1` `.2` `.3` on `192.168.100.0/24` |
| Pi4 USB | ESP32-C3 | USB | Serial **115200**, JSON @10Hz + `\n` |
| C3 GPIO2 | WS2812B DIN | dupont | 8 px, common GND |
| C3 SDA/SCL | SSD1306 | I2C `0x3C` | OLED ≤4 Hz |
| WROOM GPIO16 | Pi3a GPIO26 | jumper | Case reed, pull-up, LOW = open |
| WROOM GPIO17 | Pi3b GPIO26 | jumper | Case reed, pull-up, LOW = open |
| WROOM GPIO4 | Buzzer + | jumper | Band pattern; − → GND |
| WROOM 3V3/GND | Pi3a header | power | Tripwire stays off WiFi |
| Pi3a USB | TL-WN722N | USB | Monitor mode — passive only |
| Pi3b USB | AC600 | USB | WPA2 AP → `192.168.50.0/24` |
| Operator laptop | Pi3b AP | WiFi | **Only** Pi4:8080 allowed |
| PSU strip | 3× Pi | DC | Shared strip, ~38 W total |

**ESP32-WROOM pin map**

| Pin | Dir | Target | Logic |
|-----|-----|--------|-------|
| GPIO16 | in | Pi3a case reed | pull-up; LOW = open |
| GPIO17 | in | Pi3b case reed | pull-up; LOW = open |
| GPIO4 | out | Buzzer + | steady / double / continuous |
| 3V3 | pwr | Pi3a | — |
| GND | pwr | common | — |
| WiFi | off | — | cannot be remotely disarmed |

**ESP32-C3 pin map (→ Pi4)**

| Pin | Target | Protocol |
|-----|--------|----------|
| USB | Pi4 UART | 115200, JSON @10Hz |
| GPIO2 | WS2812B DIN | NRZ single-wire |
| GPIO4/5 | SSD1306 | I2C |
| 5V/GND | power | strip + OLED |

**Smart-house install notes:** stack three boards on a shelf or in a utility closet next to the home router/switch; keep the LED/OLED indicator in the hallway so band color is visible from the room; tripwire reeds mount on Pi3a/Pi3b case lids; management AP SSID is `SENTINEL-SECURE` (operator phone/laptop only — never IoT devices).

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
| Canary / honeypot hit | 0.25 |
| Suricata alert | 0.20 |
| Scanner finding (new CVE / open port drift) | 0.15 |
| Tripwire edge | 0.15 |
| Passive WiFi anomaly | 0.10 |
| Behavioral / scan burst residual | 0.15 |

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
| `ultron/cowrie/#` | Pi3a | risk, alert, dash | no |
| `ultron/canary/#` | Pi3a | risk, alert, dash | no |
| `ultron/lure/#` | Pi3a | risk, alert, dash | no |
| `ultron/wifi/#` | Pi3a | risk | no |
| `ultron/scan/#` | Pi4 | risk, dash | no |
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
| Honeypot | no real shells; no outbound from Cowrie jail |
| Updates | offline apt cache / vendored packages at demo |

---

## 8. Deployment Topology & Power

Shelf install in a smart house (see also §3.6 wiring):

```
[PSU strip]──Pi4, Pi3a, Pi3b          ~38W total
[5-port switch]──eth0 ×3 (+ optional uplink to home router span)
[AC600 on Pi3b]──mgmt WiFi SENTINEL-SECURE
[USB]──ESP32-C3 → Pi4 serial
[GPIO]──ESP32-WROOM → Pi3a / Pi3b case reeds + buzzer
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
| `mosquitto`, `sentinel-risk`, `sentinel-scan`, `sentinel-dashboard`, `sentinel-heal` | Pi4 Governance |
| `suricata`, `sentinel-agg`, `sentinel-cowrie-bridge`, `sentinel-canary`, `sentinel-lure` | Pi3a Detection |
| `sentinel-alert`, `sentinel-report`, `hostapd`, `dnsmasq` | Pi3b Alert |

Restart=`always` with 5s delay; health publisher every 10s on `ultron/health/#`.

---

## 10. Data Model (SQLite core)

```sql
events(id, ts, source, type, severity, payload_json);
scores(id, ts, score, band, components_json);
alerts(id, ts, sev, title, src, body, ack, ack_ts);
acks(alert_id, ts, operator);  -- or columns on alerts
scans(id, ts, tool, hosts, vulns_json, raw_path);
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
3. **Detection:** Suricata → Cowrie → canaries → lure → passive WiFi  
4. **Governance:** risk engine → scanners → SQLite  
5. **Alert:** alert manager → SMTP → reports  
6. **Dashboard last** (needs all topics) — polish until §8 of `dashboard.md` passes  
7. ESP32 firmware (C3 serial, WROOM GPIO)  
8. Full-path demo rehearsal ≤100ms + RED email  

---

## 14. Document Sync Rules

| Change | Update |
|--------|--------|
| Node/services/topics | `architecture.md` + `blackhat.md` |
| Hardware wiring / pins | `architecture.md` §3.6 + `README.md` Hardware Connections |
| Dashboard UX/perf | `dashboard.md` |
| AI assignment / quality bar | `promt.md` |
| Pitch / BOM / roadmap | `README.md` |

Same commit when possible. `ULTRON(SEN3)/` remains a frozen gitignored backup — never edit.
