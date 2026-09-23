# ULTRON — Autonomous IoT Cybersecurity Ecosystem for Smart Houses

| Field | Value |
|-------|-------|
| **Title** | ULTRON: A $290 Zero-Cloud Smart-House IoT Ecosystem for Detection, Governance, and Alert Management |
| **Domain** | **Smart houses** — home IoT endpoints (cameras, locks, hubs, sensors) |
| **Track** | **IoT** — Black Hat Asia 2027 Arsenal |
| **Phase 1 Scope** | Detection · Governance · Alert management · Premium dashboard |
| **Future Scope** | Automated response (Phase 2) · Automated threat analysis & hunting (Phase 3) |
| **Operating Mode** | **ULTRON only** (single mode) |
| **Hardware** | 3× Raspberry Pi + 2× ESP32 · ~$290 · ~38W |
| **Design rule** | Lean home/office guard — **no honeypots, no active scanners** |
| **Companion Docs** | `README.md` · `architecture.md` · `dashboard.md` · `promt.md` |
| **Repository** | https://github.com/ADITYA02NM/ULTRON |

---

## Table of Contents

1. [Abstract](#1-abstract)
2. [Introduction](#2-introduction)
3. [Design Philosophy](#3-design-philosophy)
4. [Hardware Design](#4-hardware-design)
5. [System Architecture](#5-system-architecture)
6. [Node Roles](#6-node-roles)
7. [Network Topology](#7-network-topology)
8. [Risk Scoring Engine](#8-risk-scoring-engine)
9. [Passive LAN Watch](#9-passive-lan-watch)
10. [Wireless Monitoring & IDS](#10-wireless-monitoring--ids)
11. [Health Supervision](#11-health-supervision)
12. [Alert & Reporting](#12-alert--reporting)
13. [Dashboard](#13-dashboard)
14. [ESP32 Physical Layer](#14-esp32-physical-layer)
15. [Operating Mode](#15-operating-mode)
16. [MQTT Schema Reference](#16-mqtt-schema-reference)
17. [Systemd Services Map](#17-systemd-services-map)
18. [Security Hardening](#18-security-hardening)
19. [Demo Script](#19-demo-script)
20. [Arsenal Submission](#20-arsenal-submission)
21. [Implementation Roadmap](#21-implementation-roadmap)
22. [Testing Strategy](#22-testing-strategy)
23. [Troubleshooting](#23-troubleshooting)
24. [Glossary & References](#24-glossary--references)

---

## 1. Abstract

Smart houses now embed dozens of IoT endpoints — cameras, door locks, environmental sensors, hubs, and assistants — that expand the attack surface without enterprise tooling. A Security Operations Center costs $500K–$2M per year, commercial appliances start near $2,000 plus licensing, and households that suffer a breach face immediate privacy and physical-security loss. The sensor and IoT layer of the home remains largely unmonitored: physical tampering of edge boxes, compromised microcontrollers, and rogue wireless clients fall outside conventional IDS visibility.

This paper presents **ULTRON**, a self-contained autonomous IoT cybersecurity ecosystem **for the smart house**, built on three Raspberry Pi nodes and two ESP32 microcontrollers at approximately **$290** total hardware cost, with **zero cloud dependency**. ULTRON partitions work across three pillars on dedicated hardware: **detection** (Pi3a), **governance** (Pi4 risk scoring), and **alert management** (Pi3b plus a premium single-file dashboard). Phase 1 — the scope of this paper and of the Black Hat Asia 2027 IoT Arsenal demo — implements continuous detection via a **lean sensor set** (Suricata IDS, passive LAN new-device watch, passive WiFi monitor, GPIO tripwires), a weighted 0–100 risk score with four governance bands, and operator-grade alerting (WebSocket dashboard &lt;100ms, SMTP, LED/OLED). Honeypots and active vulnerability scanners are **deliberately excluded**: they fail the resource-and-use-case test for a home/office guard box behind NAT. Automated response and automated threat analysis/hunting are explicitly deferred to future phases. The system runs fully offline in a single **ULTRON** operating mode suitable for unattended deployment in homes, apartments, and small premises.

**Keywords:** smart house, smart home, home IoT security, edge defense, risk scoring, MQTT, IDS, zero-cloud, Raspberry Pi, alert management, lean security

---

## 2. Introduction

### 2.1 Motivation

Managed detection products assume budget and staff that households and small premises do not have. Meanwhile:

- Smart-home IoT and embedded devices expand the attack surface without agent-based EDR coverage.
- Alert fatigue destroys the value of tools that only *notify* without *prioritization*.
- Cloud SIEMs create data-residency, cost, and connectivity dependencies unsuitable for isolated or air-gapped homes.
- Many DIY stacks copy enterprise patterns (honeypots, continuous scanners) that burn RAM/CPU without matching the threat model of a house behind NAT.

### 2.2 Related Tooling Gap

| Approach | Limitation for small / IoT sites |
|----------|----------------------------------|
| Cloud SIEM | Recurring cost, egress, connectivity |
| Enterprise appliance | $2K+ plus licenses; overkill |
| Single-box IDS | No physical sensors, weak prioritization, no unified operator view |
| DIY script pile | No governance model, no evidence chain, no demo-grade UX; often ships honeypot/scanner bloat |

ULTRON fills the gap with **commodity hardware**, **one message bus**, and a **score that turns events into decisions** — and by **refusing services that do not earn their place** on a lean guard box.

### 2.3 Contributions (Phase 1)

1. **Lean detection mesh** — network IDS, passive LAN new-device watch, passive WiFi, and physical tripwires on a shared MQTT contract.  
2. **Risk governance** — weighted fusion, decay, hysteresis, and four bands with **notify-only** escalation.  
3. **Zero-cloud physical feedback loop** — premium dashboard plus ESP32 LED/OLED so posture is visible without a cloud console.

### 2.4 Design Goals

| Goal | Measure |
|------|---------|
| Affordable | ≤ ~$290 BOM |
| Autonomous | 24/7 without cloud |
| Governed | Deterministic 0–100 score + bands |
| Operable | Dashboard event→pixel ≤100ms |
| Lean | No honeypot; no active scanner; every service justified |
| Honest scope | Phase 1 = detect/govern/alert only |

---

## 3. Design Philosophy

### 3.1 Principles

| Principle | Meaning |
|-----------|---------|
| Zero cloud | No CDN, SaaS, or phone-home |
| One node, one pillar | Governance / detection / alert never blur |
| Notify-first | Humans act in Phase 1; machines score and escalate |
| Evidence always | SQLite + Markdown (+ optional pendrive) |
| Fail-visible | DEGRADED banners; never silent failure |
| Cost guardrail | New hardware needs operator approval |
| **Earn your process** | A service stays only with a strong home/office use case and low RAM/CPU |

### 3.2 Pillars

```
DETECTION ──► GOVERNANCE ──► ALERT MANAGEMENT
 (Pi3a)         (Pi4)            (Pi3b + Dashboard + ESP32)
```

### 3.3 Operating Mode

**Single mode: ULTRON.** Continuous autonomous detection and governance. No alternate training, game, or mode-switch command in this release.

### 3.4 Principles of escalation

Alert-driven, human response in Phase 1. Band crossings page the operator; they do not reconfigure firewalls until Phase 2.

---

## 4. Hardware Design

### 4.1 Bill of Materials (~$290)

| Qty | Item | ~$ | Pillar |
|-----|------|----|--------|
| 1 | Raspberry Pi 4 Model B 8GB | 75 | Governance |
| 2 | Raspberry Pi 3 Model B+ 1GB | 60 | Detection + Alert |
| 1 | ESP32-C3 SuperMini | 5 | Indicator (LED/OLED) |
| 1 | ESP32-WROOM-32 devkit | 6 | Tripwire |
| 2 | USB WiFi (TL-WN722N, AC600) | 25 | Passive mon + mgmt AP |
| 1 | 5-port Gigabit switch | 20 | Production LAN |
| 3 | PSUs + cables | 35 | Power |
| 1 | SSD 240–500GB (optional evidence) | 40 | Evidence |
| — | Cases, jumpers, pendrive, misc | 24 | Support |
| | **Total** | **~$290** | |

**Power:** ≈38W total. Commodity Raspberry Pi + ESP32 boards only.

### 4.2 Form factor

Smart-house desktop/shelf stack: three boards next to the home router and switch, shared power strip, optional utility-closet mount. ESP32-C3 piggybacks USB to Pi4 (indicator in the hallway); ESP32-WROOM wires GPIO into detection/alert enclosures for physical tamper sensing.

### 4.3 Sensor attachments

| Attachment | Node | Purpose |
|------------|------|---------|
| WS2812B ×8 + SSD1306 | via ESP32-C3 | Band + score visible in room |
| Case reed/switch ×2 | ESP32-WROOM | Tamper on Pi3a / Pi3b |
| Buzzer | ESP32-WROOM | Local audible band pattern |
| TL-WN722N | Pi3a | Passive WiFi monitor |
| AC600 | Pi3b | Management AP |

### 4.4 Services deliberately excluded

| Excluded | Why it failed the lean test |
|----------|-----------------------------|
| Cowrie / SSH honeypot | Behind home NAT, scanners never reach it; multi-process Python for theater |
| Web lure / decoy login | Same exposure problem; no internet-facing surface |
| Canary files + auditd | Local-only trip; GPIO case reed already covers physical access cheaper |
| nmap / Nuclei / Lynis cadence | Active audit tools, not continuous guard; CPU spikes + noise on Pi3/Pi4 |
| Behavioral "scan burst" weight | Derived from scanners that no longer exist |

**Replacement:** passive **LAN watch** (§9) — unknown MAC joins the house network → instant low-cost signal.

---

## 5. System Architecture

### 5.1 Logical view

```
┌───────────── DETECTION (Pi3a .2) ─────────────┐
│ Suricata · LAN watch · wifi-mon · GPIO sense   │
└──────────────────────┬────────────────────────┘
                       │ MQTT ultron/#
┌───────────── GOVERNANCE (Pi4 .1) ─────────────┐
│ Mosquitto · Risk Engine · Dashboard            │
│ Health supervisor · SQLite evidence            │
└───────┬────────────────────────────┬──────────┘
        │ retained score/band        │ subscribe
        ▼                            ▼
┌── ESP32-C3 LED/OLED      ALERT (Pi3b .3) ─────┐
│                                   SMTP · reports│
│                                   mgmt AP       │
└─────────────────────────────────────────────────┘
```

### 5.2 Pipeline stages

| Stage | Name | Output |
|-------|------|--------|
| 1 | Sense | Raw events (IDS, LAN join, WiFi, GPIO) |
| 2 | Transport | MQTT `ultron/#` |
| 3 | **Govern** | Score + band (Pi4) |
| 4 | Visualize | Dashboard + LED/OLED |
| 5 | **Alert** | Email, ACK, Markdown report |
| 6 | (Future) Response | Phase 2 playbooks |
| 7 | (Future) Hunt | Phase 3 analysis |

---

## 6. Node Roles

### 6.1 Pi4 — Governance

**Hardware:** Pi 4 8GB · **IP:** 192.168.100.1  

**Role:** Central governance: MQTT broker, risk engine, **premium dashboard**, health supervision, evidence store.

| Service | Function | Port |
|---------|----------|------|
| Mosquitto | MQTT broker | 1883, 9001 WS |
| Risk Engine | Score + band | MQTT sub |
| Dashboard | Single-file operator UI | 8080 |
| Health Supervisor | Service liveness restarts | MQTT health |
| Evidence | SQLite + report index | local |

**Boot:** network → mosquitto → risk → dashboard → health → ESP32 serial → ULTRON mode.

### 6.2 Pi3a — Detection

**Hardware:** Pi 3B+ 1GB · **IP:** 192.168.100.2  

**Role:** All primary sensors — network IDS, passive LAN watch, passive wireless, tripwire sense.

| Service | Function |
|---------|----------|
| Suricata | IDS signatures on span/mirror (IDS only) |
| sentinel-lan | Passive DHCP/ARP new-device watch |
| Aggregator | Normalize → `ultron/suricata/#` |
| TL-WN722N | Passive monitor only |
| GPIO listener | `ultron/tripwire/pi3a` |

### 6.3 Pi3b — Alert

**Hardware:** Pi 3B+ 1GB · **IP:** 192.168.100.3  

**Role:** Alert delivery and operator access path.

| Service | Function | Port |
|---------|----------|------|
| Alert Manager | Persist + SMTP on RED/PURPLE | MQTT sub |
| Report generator | Daily Markdown | cron |
| hostapd | `SENTINEL-SECURE` AP | WiFi |
| dnsmasq | DHCP/DNS for mgmt | 67/53 |
| GPIO listener | `ultron/tripwire/pi3b` | — |

---

## 7. Network Topology

### 7.1 Dual-network design

| Network | Purpose | Subnet | Path |
|---------|---------|--------|------|
| Production (wired) | Smart-home hosts/IoT under watch, MQTT, dashboard | 192.168.100.0/24 | switch |
| Management (WiFi) | Operator laptop → dashboard only | 192.168.50.0/24 | Pi3b AC600 |

### 7.2 Addressing

| Host | IP |
|------|-----|
| Pi4 Governance | .1 |
| Pi3a Detection | .2 |
| Pi3b Alert | .3 |
| Monitored hosts | .10+ |
| Mgmt clients | 192.168.50.0/24 |

Firewall: deny-by-default; mgmt plane may reach **only** `192.168.100.1:8080` (plus SSH as configured).

---

## 8. Risk Scoring Engine

### 8.1 Components & weights

| Component | Weight | Source topic |
|-----------|--------|--------------|
| Suricata | 0.40 | `ultron/suricata/#` |
| Tripwire | 0.30 | `ultron/tripwire/#` |
| Passive WiFi | 0.20 | `ultron/wifi/#` |
| New device (LAN watch) | 0.10 | `ultron/lan/#` |

Weights sum to 1.00. No scanner-derived or deception-derived components.

### 8.2 Algorithm

```
score = clamp(0, 100, Σ active_component_scores)
every 10s: score = max(0, score - 2)   # decay
band = map(score) with +2 hysteresis at boundaries
publish retained: ultron/risk/score, ultron/risk/band
```

### 8.3 Bands (Phase 1 actions)

| Band | Range | LED | Phase 1 action |
|------|-------|-----|----------------|
| GREEN | 0–29 | solid | monitor |
| YELLOW | 30–59 | chase | dashboard attention |
| RED | 60–84 | strobe | **email** + alarm UI |
| PURPLE | 85–100 | pulse | escalate to operator |

### 8.4 Why scores matter

A raw alert list does not prioritize. The score is the **governance product**: one number the dashboard, LED, and email policy all share.

### 8.5 Alert generation policy

| Trigger | Alert? | Channel |
|---------|--------|---------|
| Band → YELLOW | soft | dashboard |
| Band → RED/PURPLE | hard | dashboard + SMTP |
| Single low-sev IDS | optional | feed only |
| Tripwire edge | hard | feed + risk bump |
| Unknown LAN device | soft | feed + small risk bump |

---

## 9. Passive LAN Watch

**Service:** `sentinel-lan` on Pi3a. **Passive only** — snoops DHCP/ARP (or span copies); never sends probes.

| Signal | Payload | Risk use |
|--------|---------|----------|
| Unknown MAC joins | `ultron/lan/join` | weight 0.10; yellow feed row |
| Device goes silent &gt;24h then returns | `ultron/lan/return` | informational |
| Known-device inventory | SQLite `lan_devices` | daily report |

**Why this and not nmap:** a house guard needs *who joined*, not a full port/CVE sweep every 15 minutes. ARP/DHCP watch is ~0 CPU and still answers the #1 home-ops question: *is that a new device on my network?*

Manual deep scan from dashboard remains an **operator-triggered** Phase 2+ idea — not autonomous Phase 1 behavior.

---

## 10. Wireless Monitoring & IDS

### 10.1 Passive monitoring (Phase 1)

TL-WN722N on Pi3a in **monitor mode only**: rogue/unauthorized AP detection, beacon anomalies → `ultron/wifi/#`.  

**Active wireless attacks are out of scope for Phase 1.**

### 10.2 Suricata IDS

- Runs on Pi3a (detection pillar), **IDS mode only** (alert generation; no inline blocking).  
- ET-Open / tuned local rules.  
- `eve.json` → aggregator → `ultron/suricata/#`.  
- IPS / inline enforcement = Phase 2 response design only.

---

## 11. Health Supervision

> **Phase 1 meaning:** service **liveness** — if a supervised unit is dead &gt;30s, restart it and log the incident. This is operational hygiene, not an autonomous remediation product.

### 11.1 Mechanism

- systemd `Restart=always` + `sentinel-heal` watchdog on Pi4.  
- Publish `ultron/health/{pi4,pi3a,pi3b}` every 10s.  
- Circuit breaker: after repeated failed restarts, pause 10 minutes and surface DEGRADED (prevents restart storms).

### 11.2 Out of scope (Phase 2+)

Configuration remediation playbooks, firewall edits, and autonomous containment remain **future response** work.

---

## 12. Alert & Reporting

### 12.1 Paths

| Path | Owner | When |
|------|-------|------|
| WebSocket push | Pi4 dashboard | every event ≤100ms |
| SMTP email | Pi3b alert manager | RED / PURPLE |
| LED/OLED | ESP32-C3 via Pi4 serial | every band/score |
| ACK | Dashboard → `ultron/ack/#` | operator |
| Daily Markdown | Pi3b report job | cron 00:05 |

### 12.2 Alert record

```json
{
  "id": "uuid",
  "sev": "critical",
  "title": "Suricata: ET SCAN suspicious inbound",
  "src": "pi3a",
  "body": "...",
  "ts": "2027-03-01T10:30:00Z",
  "ack": false
}
```

### 12.3 Report skeleton

Daily file `~/ultron/reports/YYYY-MM-DD.md`: band timeline, top sources, new LAN devices, open vs acked alerts, node uptime.

---

## 13. Dashboard

> **No compromise.** Spec: [`dashboard.md`](dashboard.md).

| Requirement | Value |
|-------------|-------|
| Delivery | One `index.html`, inline CSS/JS |
| Dependencies | **None** (no CDN, no build) |
| Latency | MQTT → pixel **&lt;100ms** |
| Port | Pi4 **:8080** |
| Features | Gauge, band theme, node grid, detection layers (IDS/LAN/WiFi/tripwire), alert feed + ACK, 24h chart, stats |
| States | LIVE / STALE / OFFLINE |

The dashboard is the **centerpiece of alert management** and the first thing a mentor sees.

---

## 14. ESP32 Physical Layer

### 14.1 ESP32-C3 — Indicator (USB → Pi4)

- WS2812B ring: band patterns (solid / chase / strobe / pulse)  
- SSD1306: score, band, last event, health dots  
- Serial JSON @10Hz: `{"score":42,"band":"YELLOW","nodes":4,"last":"..."}`  

### 14.2 ESP32-WROOM — Tripwire (GPIO)

- GPIO16 → Pi3a case, GPIO17 → Pi3b case (active-low, debounce 50ms)  
- Buzzer GPIO4 mirrors band  
- **No WiFi** — physically cannot be disarmed over the network  

### 14.3 Why physical feedback

Cloud dashboards fail when the network is degraded. LED/OLED keeps posture visible in the room — critical for a $290 offline story.

---

## 15. Operating Mode

### 15.1 ULTRON (sole mode)

| Aspect | Behavior |
|--------|----------|
| Sensing | Continuous (IDS, LAN, WiFi, tripwire) |
| Alerts | Full (dashboard, email, LED) |
| Governance | Always on |
| Manual tools | Operator override only — no autonomous active scan |
| Enforcement | **None** (Phase 2) |
| Stored at | `/etc/sentinel/mode` = `ULTRON` |

**Boot default:** Always ULTRON. There is no alternate mode or mode-switch MQTT command in this release.

---

## 16. MQTT Schema Reference

### 16.1 Envelope

```json
{
  "timestamp": "2027-03-01T10:30:00Z",
  "source": "pi3a-lan",
  "type": "lan_join",
  "severity": "info",
  "data": {}
}
```

### 16.2 Topics (canonical prefix `ultron/`)

| Topic | QoS | Payload highlights |
|-------|-----|-------------------|
| `ultron/risk/score` | 1 | `score`, `band`, components (retained) |
| `ultron/risk/band` | 1 | band string (retained) |
| `ultron/alert/active` | 2 | id, sev, message, source, ack |
| `ultron/suricata/#` | 1 | sig, sev, src, dst |
| `ultron/lan/#` | 1 | mac, ip, vendor, known |
| `ultron/wifi/#` | 1 | rogue AP fields |
| `ultron/tripwire/pi3a` | 2 | edge open/close |
| `ultron/tripwire/pi3b` | 2 | edge open/close |
| `ultron/health/#` | 0 | node, up, services (retained) |
| `ultron/ack/#` | 1 | alert_id, operator |
| `ultron/led/command` | 0 | color, animation |
| `ultron/mode` | 2 | always `ULTRON` (status, not a switch) |

---

## 17. Systemd Services Map

### 17.1 Pi4 Governance

| Unit | After | Restart |
|------|-------|---------|
| mosquitto.service | network-online | always |
| sentinel-risk.service | mosquitto | always |
| sentinel-dashboard.service | mosquitto | always |
| sentinel-heal.service | network | always |

### 17.2 Pi3a Detection

| Unit | After | Restart |
|------|-------|---------|
| suricata.service | network-online | always |
| sentinel-agg.service | suricata, mosquitto@Pi4 | always |
| sentinel-lan.service | network, mosquitto | always |

### 17.3 Pi3b Alert

| Unit | After | Restart |
|------|-------|---------|
| sentinel-alert.service | mosquitto, network | always |
| sentinel-report.timer | — | — |
| hostapd.service | network-online | always |
| dnsmasq.service | hostapd | always |

---

## 18. Security Hardening

| Control | Setting |
|---------|---------|
| Firewall | nftables deny-first; mgmt→8080 only |
| SSH | Keys only; no password |
| MQTT | Auth + ACL (only Pi4 writes `risk/#`) |
| Dashboard | LAN bind; no WAN; optional basic auth |
| Secrets | `/etc/sentinel/*` root:600 |
| Updates | Offline cache before demo |
| Evidence | Append-only daily files + hashes in report |

---

## 19. Demo Script

| Time | Action | Mentor takeaway |
|------|--------|-----------------|
| 0:00 | Show BOM + power strip on | $290, no cloud laptop hotspot needed |
| 0:30 | Open dashboard LIVE | Risk number + band in &lt;3s |
| 1:00 | Trigger Suricata rule or LAN join on Pi3a | Score climbs; feed fills |
| 1:30 | Watch LED + OLED | Physical governance |
| 2:00 | Cross RED (or simulate) | Email + alarm state |
| 2:30 | ACK alert | Operator loop closes |
| 3:00 | Point at three boards | Detect · Govern · Alert pillars |
| 3:30 | Name what we **cut** and why | Lean guard: no honeypot/scanner bloat |
| 4:00 | Q\&A | `architecture.md` + `dashboard.md` |

---

## 20. Arsenal Submission

| Field | Value |
|-------|-------|
| **Tool Name** | ULTRON — Smart-House IoT Cybersecurity Ecosystem |
| **Category** | **IoT** |
| **Repository** | https://github.com/ADITYA02NM/ULTRON |
| **Hardware** | 3× Raspberry Pi, 2× ESP32, ~$290 |
| **License** | MIT |

**Abstract (≈150 words):**  
ULTRON is a zero-cloud IoT security ecosystem for the smart house, built on three Raspberry Pis and two ESP32s (~$290). Phase 1 delivers lean detection (Suricata IDS, passive LAN new-device watch, passive WiFi, GPIO tripwires — no honeypots or active scanners), governance (weighted 0–100 risk score with GREEN/YELLOW/RED/PURPLE bands, decay, hysteresis), and alert management (sub-100ms single-file dashboard, SMTP on critical bands, LED/OLED physical indicators, acknowledgement and Markdown evidence). Nodes are pillar-isolated: Pi4 governance, Pi3a detection, Pi3b alert. The system runs autonomously offline in a single ULTRON mode for homes and small premises. Automated response and automated threat analysis/hunting are documented as future phases and intentionally not shipped in Phase 1. The demo shows an end-to-end detect → govern → alert loop visible on screen and in hardware.

**Audience takeaways:**

1. How to prioritize IoT alerts with a transparent risk score  
2. Pillar-isolated design on three cheap SBCs  
3. Physical (LED/OLED) feedback without cloud  
4. A demo-grade dashboard with zero dependencies  
5. A **lean sensor set** that proves you can guard a home without honeypot/scanner bloat  

---

## 21. Implementation Roadmap

### 21.1 Phase 1 — Black Hat (build now)

| Day | Work |
|-----|------|
| 1–2 | Images, IPs, firewall, Mosquitto |
| 3–5 | Detection stack (Suricata, sentinel-lan, passive WiFi) |
| 6–8 | Risk engine + SQLite |
| 9–11 | Alert manager + SMTP + reports |
| 12–16 | **Dashboard polish to `dashboard.md` gate** |
| 17–18 | ESP32 firmware |
| 19–21 | Full-path latency + RED email rehearsal |
| 22–28 | Docs, video, Arsenal submit |

### 21.2 Phase 2 — Future: response

Band-keyed reversible playbooks (nftables, restarts), audit trail. **Not in Phase 1 code.**

### 21.3 Phase 3 — Future: threat analysis & hunting

Baselines, correlation, hypothesis sweeps. **Concept only** for this paper.

---

## 22. Testing Strategy

### 22.1 Unit

| Component | Case | Expect |
|-----------|------|--------|
| Risk | empty events | score 0 GREEN |
| Risk | one Suricata hit | +40 weight path |
| Risk | decay | −2 / 10s |
| Risk | clamp | never &lt;0 or &gt;100 |
| Health supervisor | 3 failed restarts | breaker opens 10 min |
| LAN watch | known MAC | no event |
| LAN watch | unknown MAC | `ultron/lan/join` |

### 22.2 Integration

| Case | Expect |
|------|--------|
| Suricata → score → LED | band changes ≤5s |
| LAN join → dashboard | feed row &lt;100ms to pixel |
| Tripwire → email (if RED path) | ≤30s SMTP |
| Kill Mosquitto | STALE/OFFLINE ≤5s |
| ACK | badge clears; survives refresh |

### 22.3 Hardware validation

| Test | Pass |
|------|------|
| Power per rail | within PSU rating |
| Pi4 temp 24h | &lt;70°C |
| Mgmt WiFi | dashboard at 30m |
| Tripwire ×100 | zero missed |
| Boot → GREEN LED | &lt;90s |
| Steady-state load (Pi3a) | Suricata+lan+agg under agreed RAM/CPU budget |

---

## 23. Troubleshooting

### 23.1 Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| LED off | serial link down | check USB, udev, restart C3 |
| Score stuck 0 | risk not sub’d | mosquitto up; credentials |
| Dashboard offline | WS/port | 8080 + 9001 path |
| No email | SMTP config | test from Pi3b; `/etc/sentinel/smtp.conf` |
| No LAN events | sentinel-lan down | `systemctl status sentinel-lan` |
| Health breaker open | restart loop | wait 10m; check unit |
| AP missing | hostapd/dnsmasq | status + AC600 link |
| Tripwire dead | wire | continuity test |
| Disk full | logs | journal vacuum; logrotate |

### 23.2 Debug commands

| Purpose | Command |
|---------|---------|
| Services | `systemctl status mosquitto sentinel-* suricata` |
| Bus | `mosquitto_sub -h localhost -t 'ultron/#' -v` |
| Score | `mosquitto_sub -h localhost -t 'ultron/risk/score' -C 1` |
| Suricata | `tail -f /var/log/suricata/fast.log` |
| LAN watch | `journalctl -u sentinel-lan -f` |
| Temp | `vcgencmd measure_temp` |

---

## 24. Glossary & References

### 24.1 Glossary

| Term | Definition |
|------|------------|
| **ULTRON** | Unified Layer for Threat Response, Observability & Network defense |
| **Risk Score** | 0–100 integer from weighted event fusion |
| **Risk Band** | GREEN / YELLOW / RED / PURPLE bucket |
| **Suricata** | Network IDS engine (IDS-only in Phase 1) |
| **LAN watch** | Passive DHCP/ARP new-device detection |
| **Tripwire** | GPIO case-tamper sensor |
| **Health Supervisor** | Liveness restart + circuit breaker (Phase 1) |
| **MQTT** | Lightweight pub/sub protocol |
| **Mosquitto** | Open-source MQTT broker |
| **nftables** | Kernel packet filter (deny-first config) |
| **Notify-only** | Phase 1 escalation without automated enforcement |
| **Pillar** | Governance (Pi4), Detection (Pi3a), Alert (Pi3b) |
| **Lean guard** | Every service must justify RAM/CPU against home/office threat model |

### 24.2 References

1. Mosquitto MQTT Broker — https://mosquitto.org  
2. Suricata — https://suricata.io  
3. nftables — https://www.netfilter.org/projects/nftables/  
4. ESP32 Arduino Core — https://github.com/espressif/arduino-esp32  
5. Adafruit NeoPixel — https://github.com/adafruit/Adafruit_NeoPixel  
6. Raspberry Pi Documentation — https://www.raspberrypi.com/documentation/  
7. MQTT v3.1.1 — https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html  
8. MIT License — https://opensource.org/licenses/MIT  

---

> **Document Version:** 8.0  
> **Last Updated:** September 2026  
> **License:** MIT  
> **Repository:** https://github.com/ADITYA02NM/ULTRON  
> **Scope lock:** Phase 1 = detection · governance · alert management · premium dashboard · lean sensors only.  
> Future = response + automated threat analysis/hunting only.  
> **Explicitly out:** honeypots, active scanners, dual modes, cloud, GPU boards.
