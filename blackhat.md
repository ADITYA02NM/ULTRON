# ULTRON — Autonomous Cybersecurity Suite

> **Unified Layer for Threat Response, Observability & Network Defense**
> Black Hat Asia 2027 Arsenal Submission

---

| Field | Value |
|-------|-------|
| **Project** | ULTRON — Autonomous Cybersecurity Suite |
| **License** | MIT |
| **Total Cost** | ~$290 (3 Raspberry Pi nodes + peripherals) |
| **Hardware** | 3× Raspberry Pi, 2× ESP32, 500GB SSD, TL-WN722N, AC600, 128GB pendrive |
| **Target Audience** | Small companies, schools, universities, home labs |
| **Operating Modes** | ULTRON (full protection) + LAB (CTF training) |
| **Dashboard** | Single-file HTML, live WebSocket updates |
| **Reports** | Markdown (.md) files |
| **Event Bus** | Mosquitto MQTT |
| **Database** | SQLite (WAL mode) |
| **Minimum Admin** | 1 person (or fully autonomous) |

---

## Table of Contents

1. [Abstract](#1-abstract)
2. [Introduction](#2-introduction)
3. [Design Philosophy](#3-design-philosophy)
4. [Hardware Design](#4-hardware-design)
5. [System Architecture](#5-system-architecture)
6. [Node Roles](#6-node-roles)
7. [Network Topology](#7-network-topology)
8. [MQTT Event Bus](#8-mqtt-event-bus)
9. [Risk Scoring Engine](#9-risk-scoring-engine)
10. [Scanner Engine](#10-scanner-engine)
11. [Deception Layer](#11-deception-layer)
12. [Wireless Attacks & IDS](#12-wireless-attacks--ids)
13. [Self-Healing Framework](#13-self-healing-framework)
14. [Alert & Reporting](#14-alert--reporting)
15. [Dashboard](#15-dashboard)
16. [ESP32 Physical Layer](#16-esp32-physical-layer)
17. [Operating Modes](#17-operating-modes)
18. [LAB / CTF Mode](#18-lab--ctf-mode)
19. [MQTT Schema Reference](#19-mqtt-schema-reference)
20. [Systemd Services Map](#20-systemd-services-map)
21. [Security Hardening](#21-security-hardening)
22. [Demo Script](#22-demo-script)
23. [Arsenal Submission](#23-arsenal-submission)
24. [Implementation Roadmap](#24-implementation-roadmap)
25. [Testing Strategy](#25-testing-strategy)
26. [ULTRON-X: NVIDIA Jetson Nano Variant](#26-ultron-x-nvidia-jetson-nano-variant)
27. [Troubleshooting](#27-troubleshooting)
28. [Glossary & References](#28-glossary--references)

---

## 1. Abstract

ULTRON is a self-contained, autonomous cybersecurity appliance built entirely on Raspberry Pi hardware. It is a **modular device** — connect it to any server room via Ethernet and it immediately begins monitoring, detecting, scanning, and protecting. It continuously monitors wired LAN traffic for threats, operates honeypots to lure attackers, performs authorized vulnerability scans against production servers, and assists remediation — all without requiring a dedicated security team. Operator management happens over a separate WiFi hotspot, keeping the production network clean. Physical LED and OLED indicators communicate real-time threat posture at a glance.

The core innovation is a **risk-scoring engine** that fuses signals from multiple detection layers — network scanning, honeypot canary events, intrusion detection, wireless monitoring, and physical tripwire sensors — into a single 0–100 risk score. This score drives automated response: from passive monitoring at green, through active defense at yellow, to full quarantine at red. A self-healing subsystem uses predefined remediation templates to automatically fix common issues like unauthorized SSH access, open ports, or expired TLS certificates.

ULTRON operates in two modes: **ULTRON** (full autonomous protection with active scanning and response) and **LAB** (educational CTF mode where students learn offensive and defensive security against a live system). The dual-mode design makes it both a production security appliance and a hands-on training platform.

The entire system costs approximately $290 in hardware, runs on open-source software, and requires zero cloud connectivity. It is designed for environments where enterprise security solutions are too expensive or too complex — schools, small businesses, community labs, and home networks.

**Keywords:** Autonomous security, Raspberry Pi, honeypot, risk scoring, self-healing, CTF, network monitoring, intrusion detection, zero cloud dependency

---

## 2. Introduction

### 2.1 Problem Statement

Small organizations — schools, small businesses, community labs — face the same cybersecurity threats as large enterprises but lack the resources to address them. A dedicated Security Operations Center (SOC) costs $500K–$2M annually. Managed Security Service Providers (MSSPs) charge $5K–$20K/month. Commercial appliances like Fortinet or Palo Alto start at $2,000 for the hardware alone, plus ongoing licensing fees.

ULTRON solves this as a **modular appliance** — a single portable device that plugs into any server room's Ethernet switch and immediately begins protecting the network. No cloud setup, no agent installation on servers, no complex configuration. Connect the cable, power on, and ULTRON scans, monitors, and defends the wired LAN autonomously.

The result is a massive security gap: 60% of small businesses that suffer a cyberattack close within 6 months. Schools and universities are the most targeted sector for ransomware. Yet the tools available to these organizations are either too expensive, too complex, or too passive (they detect but do not respond).

### 2.2 The Gap

Existing open-source security tools address individual pieces of the puzzle:

| Tool | What It Does | What It Lacks |
|------|-------------|---------------|
| Snort / Suricata | Network intrusion detection | No automated response, no self-healing |
| Cowrie | SSH honeypot | No integration with risk scoring |
| Nessus / OpenVAS | Vulnerability scanning | Manual scheduling, no auto-remediation |
| Wazuh | Security monitoring | Enterprise complexity, requires agents on every host |
| Security Onion | Full SOC platform | Requires powerful hardware, steep learning curve |

No single open-source solution combines monitoring, deception, scanning, risk scoring, automated remediation, and physical indicators into a cohesive, autonomous package that runs on a $75 Raspberry Pi.

### 2.3 Contributions

This paper presents three contributions:

1. **Unified Autonomous Security Appliance** — A single system integrating network monitoring (Suricata IDS), honeypot deception (Cowrie + canary files), vulnerability scanning (nmap + Nuclei + Lynis), and automated self-healing into a cohesive pipeline driven by MQTT pub/sub messaging.

2. **Hardware-in-the-Loop Risk Scoring** — A deterministic risk engine that fuses six signal sources into a single 0–100 score, driving both software response (firewall rules, service restarts) and physical indicators (ESP32 NeoPixel LED color, OLED display, tripwire alerts). The score decays over time, ensuring transient events do not permanently lock the system.

3. **Dual-Mode Educational Platform** — A LAB mode that transforms the security appliance into a live CTF training environment, where students perform scans, crack defenses, and earn leaderboard points — all against a real, functioning security stack rather than artificial challenges.

### 2.4 Design Goals

| Goal | Approach |
|------|----------|
| Zero cloud dependency | All processing local, MQTT internal network only |
| Minimal administration | Automated scanning, scoring, and remediation |
| Observable security posture | ESP32 LED + OLED provide instant visual feedback |
| Affordable | $290 total hardware cost, open-source software |
| Educational | LAB mode transforms appliance into CTF platform |
| Autonomous operation | System runs 24/7 without human intervention |
| Fail-safe defaults | Deny-all firewall, services fail closed |

---

## 3. Design Philosophy

### 3.1 Modular Dual-Network Architecture

ULTRON is a **modular security appliance** — a portable, self-contained device that plugs into any server room and immediately begins protecting the network. It operates on two physically separated networks:

**Wired LAN (Production Monitoring):**
- All three Raspberry Pis connect to the server room's Ethernet switch via the 5-port switch
- nmap scans target production servers on the wired LAN
- Suricata monitors all LAN traffic for intrusion detection
- Cowrie honeypot listens on the wired network for SSH attempts
- Communication with managed servers happens over Ethernet only

**WiFi Hotspot (Operator Management):**
- AC600 on Pi3b creates `SENTINEL-SECURE` WiFi access point
- Operator connects laptop to this WiFi to access the dashboard
- No production traffic flows through the WiFi network
- Management plane is physically isolated from the monitoring plane

This dual-network design has three advantages:
- **No interference with production** — scanning and monitoring happen on the wired LAN without disrupting WiFi or internet for end users
- **Management isolation** — operator access is on a separate wireless network, so compromising the WiFi does not expose the monitoring infrastructure
- **Plug-and-play deployment** — connect the Ethernet cable to the server room switch, power on, and ULTRON begins protecting the wired LAN immediately

### 3.2 Fail-Closed Defaults

Every component follows a fail-closed philosophy:

| Component | Fail-Open Behavior | Fail-Closed Behavior (ULTRON) |
|-----------|-------------------|-------------------------------|
| Firewall (nftables) | Allow all traffic | Drop all traffic except explicit rules |
| MQTT broker | Accept anonymous connections | Require authentication + ACL |
| SSH access | Password login | Key-based only, rate-limited |
| Scanning | Scan only when requested | Scan on schedule (every 15 min) |
| Self-healing | Log and alert only | Detect + fix + verify + log |
| Dashboard | Show everything | Show only authenticated sessions |

### 3.3 Dual-Mode Architecture

ULTRON operates in exactly two modes:

**ULTRON Mode** — Full autonomous protection. All services active: scanning, deception, IDS, self-healing, alerting. The system operates 24/7 without human intervention. Risk scoring drives automated response. ESP32 LED shows real-time threat posture.

**LAB Mode** — Educational CTF training. Scanning is student-initiated (not automated). Automated defense responses are disabled (honeypot and canaries remain active as CTF targets). Leaderboard tracks student achievements. Students perform vulnerability assessments, crack defenses, and learn security concepts against a live system.

The mode is selected at boot and stored in `/etc/sentinel/mode`. Switching modes requires restarting MQTT-triggered services.

### 3.4 Operating Principles

1. **Observability first** — Every event is logged, scored, and displayed. The operator always knows the system state.
2. **Automated response, human oversight** — The system fixes what it can automatically. Unfixable issues escalate to the operator via email.
3. **Defense in depth** — Multiple overlapping detection layers ensure no single point of failure in detection.
4. **Physical + digital feedback** — Threat posture is communicated both digitally (dashboard, email) and physically (LED color, OLED text, tripwire buzzer).
5. **No external dependencies** — Everything runs locally. No cloud services, no API keys, no internet required.

---

## 4. Hardware Design

### 4.1 Bill of Materials

| # | Component | Specification | Qty | Cost | Purpose |
|---|-----------|--------------|-----|------|---------|
| 1 | Raspberry Pi 4 Model B | 8GB RAM, BCM2711 | 1 | $75 | Brain — core engine, dashboard, scanner, MQTT broker |
| 2 | Raspberry Pi 3 Model B+ | 1GB RAM, BCM2837B0 | 1 | $30 | Attack node — honeypot, wireless attacks, canary |
| 3 | Raspberry Pi 3 Model B+ | 1GB RAM, BCM2837B0 | 1 | $30 | IDS & Gateway — Suricata IDS/IPS, WiFi AP, dashboard aggregator |
| 4 | SanDisk Ultra 500GB | USB 3.0 SSD | 1 | $35 | NAS storage, logs, evidence vault |
| 5 | SanDisk Ultra 128GB | microSD (Class 10, A2) | 1 | $8 | Evidence pendrive (Pi4, evidence vault) |
| 6 | ESP32-C3 SuperMini | RISC-V 160MHz, WiFi | 1 | $4 | NeoPixel threat light + OLED status display |
| 7 | WS2812B NeoPixel Ring | 8 LEDs, RGB | 1 | $3 | Visual threat indicator |
| 8 | SSD1306 OLED | 0.96" 128×64, I2C | 1 | $3 | Text status display |
| 9 | ESP32-WROOM-32 | Dual-core 240MHz, WiFi | 1 | $5 | Tripwire sensors + WiFi portal + debug server |
| 10 | TP-Link TL-WN722N | v1/v2, Atheros AR9271 | 1 | $12 | Monitor mode + packet injection (Pi3a) |
| 11 | TP-Link AC600 | Archer T2U Nano USB | 1 | $12 | WiFi hotspot access point (Pi3b) |
| 12 | 5-Port Ethernet Switch | Unmanaged, 100Mbps | 1 | $12 | LAN backbone connecting all Pi nodes |
| 13 | USB 2.0 Hub | 4-port, powered | 1 | $5 | Pi4 USB expansion |
| 14 | 30AWG Silicone Wire | Assorted colors, 3m | 1 | $4 | GPIO wiring, tripwire connections |
| 15 | 10kΩ Resistors | 1/4W, through-hole | 5 | $1 | Pull-up/pull-down for tripwire GPIO |
| 16 | Passive Buzzer | 5V, 85dB | 1 | $1 | Tripwire alarm (ESP32-WROOM) |
| 17 | Y-Splitter Cable | AC power, 2-way | 1 | $4 | Power distribution |
| 18 | 5V 3A DC Barrel Adapter | Micro-USB or USB-C | 1 | $4 | Pi4 power supply |
| 19 | 5V 2.5A DC Barrel Adapter | Micro-USB | 2 | $8 | Pi3a and Pi3b separate power supplies |
| 20 | USB Fan (5V) | 80mm, quiet | 1 | $3 | Active cooling for Pi4 |
| | | | **Total** | **~$263** | |

**Optional:**

| Component | Cost | Purpose |
|-----------|------|---------|
| TP-Link AC600 (second) | $12 | Dedicated attack interface on Pi3a |
| USB-to-Serial Adapter | $5 | ESP32 debug console |
| 3D Printed Case | $10 | Enclosure for all components |

### 4.2 Wiring & GPIO Reference

**ESP32-C3 to NeoPixel + OLED:**

| ESP32-C3 GPIO | Component | Connection |
|---------------|-----------|------------|
| GPIO8 | NeoPixel DIN | Data line (power from Pi4 USB, shared GND) |
| GPIO5 | OLED SDA | I2C data to SSD1306 |
| GPIO6 | OLED SCL | I2C clock to SSD1306 |
| 5V | NeoPixel VCC | Power from Pi4 USB port |
| GND | Common GND | Shared ground with Pi4 |

**ESP32-WROOM Tripwire Connections:**

| WROOM GPIO | Pi Connection | Sensor |
|------------|--------------|--------|
| GPIO16 | Pi3a GPIO17 (via 30AWG wire) | Attack & Honeypot enclosure sensor |
| GPIO17 | Pi3b GPIO27 (via 30AWG wire) | IDS & Gateway enclosure sensor |
| GPIO4 | Passive buzzer | Tripwire alarm output |

Both GPIO16 and GPIO17 use internal pull-up resistors. Tripwire triggers when the pin is pulled LOW (enclosure opened, wire cut). The buzzer sounds for 2 seconds on trigger, then the event is published via MQTT.

**Raspberry Pi GPIO Assignments:**

| Pi | GPIO | Direction | Purpose |
|----|------|-----------|---------|
| Pi4 | GPIO17 | Output | Status LED (green = healthy, red = fault) |
| Pi3a | GPIO17 | Input (pull-up) | Tripwire sensor to ESP32-WROOM GPIO16 |
| Pi3b | GPIO27 | Input (pull-up) | Tripwire sensor to ESP32-WROOM GPIO17 |

### 4.3 Power Distribution

```
AC Outlet (230V)
├── DC 5V 3A Adapter ──── Pi4 (USB-C)
│                           └── USB Hub ── ESP32-C3 (NeoPixel + OLED)
│                                     └── 500GB SSD
├── DC 5V 2.5A Adapter ── Pi3a (Micro-USB) + TL-WN722N
└── DC 5V 2.5A Adapter ── Pi3b (Micro-USB) + AC600

USB Fan ── Pi4 USB port (5V 0.5A)
```

> **Power Note:** Pi3a and Pi3b must use separate power adapters. Pi3a draws ~6.5W (5W + TL-WN722N 1.5W) and Pi3b draws ~7.5W (5W + AC600 2.5W). A single 2.5A adapter (12.5W) cannot supply both. Use two separate 2.5A adapters.

**Power Budget:**

| Component | Voltage | Current | Power |
|-----------|---------|---------|-------|
| Pi4 8GB | 5V | 3.0A (max) | 15W |
| Pi3a | 5V | 1.0A | 5W |
| Pi3b | 5V | 1.0A | 5W |
| SSD (500GB) | 5V | 0.5A | 2.5W |
| AC600 WiFi | 5V | 0.5A | 2.5W |
| TL-WN722N | 5V | 0.3A | 1.5W |
| NeoPixel (8 LEDs) | 5V | 0.3A | 1.5W |
| OLED | 3.3V | 0.02A | 0.07W |
| ESP32-C3 | 5V | 0.1A | 0.5W |
| ESP32-WROOM | 5V | 0.2A | 1W |
| USB Fan | 5V | 0.2A | 1W |
| Switch | 5V | 0.5A | 2.5W |
| **Total** | | | **~38W** |

### 4.4 Physical Deployment

```
┌─────────────────────────────────────────────────────┐
│                 ULTRON PHYSICAL LAYOUT                │
│                                                       │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│   │  Pi4    │  │  Pi3a   │  │  Pi3b   │              │
│   │  Brain  │  │  Attack │  │  IDS    │              │
│   │ 8GB RAM │   │ 1GB     │  │ 1GB     │              │
│   └────┬────┘  └────┬────┘  └────┬────┘              │
│        │            │            │                    │
│   ┌────┴────┐  ┌────┴────┐  ┌────┴────┐              │
│   │USB Hub  │  │TL-WN722N│  │AC600    │              │
│   │SSD+ESP32│  │Monitor  │  │Hotspot  │              │
│   └─────────┘  └─────────┘  └─────────┘              │
│        │            │            │                    │
│   ┌────┴────────────┴────────────┴────┐               │
│   │        5-Port Ethernet Switch      │               │
│   └───────────────────────────────────┘               │
│                                                       │
│   ┌─────────┐  ┌─────────┐                           │
│   │ESP32-C3 │  │ESP32-WR │                           │
│   │NeoPixel │  │Tripwire │                           │
│   │OLED     │  │Portal   │                           │
│   └─────────┘  └─────────┘                           │
│                                                       │
│   ┌─────────┐                                        │
│   │500GB SSD│  ← USB 3.0 to Pi4                     │
│   │NAS/Vault│                                        │
│   └─────────┘                                        │
└─────────────────────────────────────────────────────┘
```

### 4.5 USB Topology

**Pi4 USB Ports (4 total):**
- USB 3.0 Port 1 → 500GB SSD (NAS storage + evidence vault)
- USB 3.0 Port 2 → (available)
- USB 2.0 Port 1 → USB 2.0 Hub
  - Hub Port 1 → ESP32-C3 (NeoPixel + OLED)
  - Hub Port 2 → ESP32-WROOM (data cable, serial + power)
  - Hub Port 3 → 128GB pendrive (evidence vault)
  - Hub Port 4 → (available)
- USB 2.0 Port 2 → USB Fan (5V power)

**Pi3a USB Port (1):**
- TL-WN722N WiFi adapter (monitor mode + packet injection)

**Pi3b USB Port (1):**
- AC600 WiFi adapter (creates SENTINEL-SECURE hotspot)

---

## 5. System Architecture

### 5.1 System Overview

ULTRON follows a **distributed microservices architecture** with MQTT as the central event bus. Each Raspberry Pi runs independent services that communicate exclusively through MQTT publish/subscribe messaging. There are no direct HTTP calls between nodes — all inter-node communication is event-driven.

**Network topology:**
```
┌────────────────────────────────────────────────────────────────────┐
│                     SERVER ROOM (Production LAN)                    │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │Server 1 │  │Server 2 │  │Server 3 │  │ ...     │              │
│  │192.168. │  │192.168. │  │192.168. │  │         │              │
│  │100.10   │  │100.20   │  │100.30   │  │         │              │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘              │
│       │            │            │            │                     │
│       └────────────┴────────────┴────────────┘                     │
│                          │ Ethernet                                │
│                          │                                         │
│                   ┌──────┴──────┐                                  │
│                   │  5-Port     │ ← ULTRON plugs in here          │
│                   │  Switch     │                                  │
│                   └──────┬──────┘                                  │
└──────────────────────────┼─────────────────────────────────────────┘
                           │
              ┌────────────┼────────────────┐
              │            │                │
         ┌────┴────┐  ┌───┴─────┐    ┌─────┴─────┐
         │   Pi4   │  │  Pi3a   │    │   Pi3b    │
         │  Brain  │  │ Attack  │    │    IDS    │
         │ .10     │  │  .20    │    │    .30    │
         └─────────┘  └─────────┘    └─────┬─────┘
                                           │
                                 ┌─────────┴─────────┐
                                 │  WiFi: SENTINEL-   │ ← Operator management only
                                 │  SECURE (AC600)    │
                                 └─────────┬─────────┘
                                           │
                                      ┌────┴────┐
                                      │ Operator│
                                      │ Laptop  │
                                      └─────────┘
```

**Key principle:** The 5-port switch connects ULTRON's three Pi nodes to the server room's production LAN. The Scanner Engine on Pi4 scans production servers (192.168.100.0/24). Suricata on Pi3b monitors all production traffic flowing through the switch. The WiFi hotspot (AC600) is a separate management network that does not carry production traffic.

### 5.2 Data Flow Pipeline

Every security event follows the same six-stage pipeline:

```
DETECT → COLLECT → SCORE → DECIDE → RESPOND → REPORT
  │         │         │        │         │         │
  │         │         │        │         │         └─ Dashboard + Email + .md report
  │         │         │        │         └───────── Firewall rules + service restart + LED
  │         │         │        └─────────────────── Risk band threshold check
  │         │         └──────────────────────────── clamp(0..100, Σ components × weights)
  │         └───────────────────────────────────── MQTT canary/ids/scan/tripwire events
  └─────────────────────────────────────────────── Sensor detects anomaly (network/physical)
```

**Stage 1 — DETECT:** Sensors detect anomalies across the wired LAN. nmap discovers open ports on production servers. Suricata sees suspicious packets on the Ethernet switch. Cowrie records SSH login attempts. Canary files are accessed. Tripwire GPIO triggers.

**Stage 2 — COLLECT:** Each sensor publishes an MQTT event to its designated topic. Events include timestamp, source IP (production server or attacker), event type, severity, and raw payload. The MQTT broker ensures reliable delivery (QoS 1 for critical events).

**Stage 3 — SCORE:** The Risk Engine subscribes to all `sentinel/+` topics. Each incoming event adds to the risk score using the formula: `clamp(0..100, Σ component_score × weight)`. The score decays by 2 points every 10 seconds toward baseline (0).

**Stage 4 — DECIDE:** The engine compares the current score against risk band thresholds:
- 0–29: GREEN (normal operations, breathing LED)
- 30–59: YELLOW (active defense, chasing LED)
- 60–84: RED (critical alerts, strobe LED)
- 85–100: PURPLE (full quarantine, pulsing LED)

**Stage 5 — RESPOND:** Based on the risk band:
- GREEN: No action. Continue monitoring.
- YELLOW: Increase scan frequency. Enable additional logging.
- RED: Activate Suricata IPS mode. Block suspicious IPs. Send email alert.
- PURPLE: Full network quarantine (nftables drop-all). Tripwire buzzer. Purple LED pulse.

**Stage 6 — REPORT:** Events are logged to SQLite. Dashboard updates via WebSocket. Email alerts sent for RED and PURPLE bands. Markdown reports generated daily.

### 5.3 Inter-Node Communication

All communication between nodes happens through MQTT. There are no direct HTTP calls or SSH tunnels between nodes.

| Source | Topic | Destination | Payload |
|--------|-------|-------------|---------|
| Pi3a | `sentinel/canary` | Pi4 Risk Engine | File access event (type, file, user, confidence) |
| Pi3a | `sentinel/heartbeat` | Pi4 Risk Engine | Node health (uptime, CPU, memory, disk) |
| Pi4 | `sentinel/risk` | Pi3b Aggregator | Risk score + band + timestamp |
| Pi4 | `sentinel/alert` | Pi3b Aggregator + Email | Alert details (severity, message, action taken) |
| Pi4 | `sentinel/scan` | Pi3b Aggregator | Scan results (hosts, ports, vulnerabilities) — targets are production servers on the wired LAN |
| Pi4 | `sentinel/led` | ESP32-C3 | LED command (color, animation pattern) |
| Pi3b | `sentinel/ids` | Pi4 Risk Engine | Suricata alert (signature, source IP, severity) — from production LAN traffic |
| Pi4 | `sentinel/mode` | All nodes | Mode change (ULTRON or LAB) |
| ESP32-WROOM | `sentinel/tripwire` | Pi4 Risk Engine | Physical sensor trigger (GPIO, timestamp) |
| Pi4 | `sentinel/selfheal` | Pi3b Aggregator | Remediation action (what, result, timestamp) |

---

## 6. Node Roles

### 6.1 Pi4 — The Brain

**Hardware:** Raspberry Pi 4 Model B, 8GB RAM
**IP:** 192.168.100.1 (LAN), built-in WiFi (802.11ac)
**Role:** Central orchestrator. Runs the MQTT broker, risk engine, scanner engine (targets production servers on the wired LAN), self-healing engine, alert system, dashboard, and evidence manager.

**Services running:**

| Service | Function | Port |
|---------|----------|------|
| Mosquitto | MQTT message broker | 1883 (MQTT), 9001 (WebSocket) |
| Risk Engine | Score computation + band classification | Internal (MQTT subscriber) |
| Scanner Engine | nmap + Nuclei + Lynis — scans production servers on wired LAN | Internal (MQTT publisher) |
| Self-Healer | TOML remediation templates + circuit breaker | Internal (MQTT subscriber) |
| Alert System | Email notifications (SMTP) | Internal (MQTT subscriber) |
| Dashboard | Single-file HTML status page | 8080 (HTTP) |
| Evidence Manager | Log rotation + pendrive sync | Internal (cron-triggered) |

**Boot sequence:**
1. Kernel boots → systemd starts
2. Network interface configured (static IP 192.168.100.1)
3. Mosquitto broker starts (must start first — all other services depend on it)
4. Risk engine starts (subscribes to all sentinel/+ topics)
5. Scanner engine starts (registers 15-minute timer)
6. Self-healing engine starts (loads TOML templates)
7. Alert system starts (configures SMTP connection)
8. Dashboard starts (serves on port 8080)
9. ESP32-C3 connection established (USB serial)
10. System enters ULTRON mode (default) or LAB mode (if configured)

### 6.2 Pi3a — Attack & Honeypot Node

**Hardware:** Raspberry Pi 3 Model B+, 1GB RAM
**IP:** 192.168.100.2 (LAN)
**Role:** Wireless security assessment, honeypot (Cowrie on wired LAN), canary monitoring (auditd + web lure). Also runs wireless attacks via TL-WN722N (LAB mode).

**Services running:**

| Service | Function | Port |
|---------|----------|------|
| Canary Bridge | Monitors Cowrie logs + auditd events | Internal (MQTT publisher) |
| Web Lure | Fake admin login page on port 80 | 80 (HTTP) |
| Cowrie | SSH honeypot (port 22) | 22 (SSH) |
| auditd | File access monitoring for canary files | Internal (kernel) |

**Key behaviors:**
- **Canary Bridge** tails two log files simultaneously:
  1. Cowrie JSON log — records every SSH login attempt and command executed
  2. Auditd log — records access to canary files (fake credentials, fake SSH keys)
- Each event is classified by type (login_attempt, command_execution, file_read, file_copy) and published to `sentinel/canary`
- **Web Lure** serves a realistic-looking admin panel on port 80. Any login attempt is logged and published as a canary event.
- **TL-WN722N** adapter is available in monitor mode for wireless packet capture and deauthentication testing (LAB mode only).

### 6.3 Pi3b — IDS & Gateway Node

**Hardware:** Raspberry Pi 3 Model B+, 1GB RAM
**IP:** 192.168.100.3 (LAN)
**Role:** WiFi hotspot operator (AC600), Suricata IDS/IPS (monitors production LAN traffic via wired Ethernet), dashboard aggregator, network gateway for WiFi management clients.

**Services running:**

| Service | Function | Port |
|---------|----------|------|
| Suricata | Network intrusion detection/prevention | Internal (AF_PACKET) |
| Dashboard Aggregator | REST API for dashboard data | 8080 (HTTP) |
| AC600 AP | WiFi hotspot (SENTINEL-SECURE) | 2.4GHz/5GHz |
| dnsmasq | DHCP + DNS for WiFi clients | 67 (DHCP), 53 (DNS) |

**Key behaviors:**
- **Suricata** runs in IDS mode (ULTRON) or IPS mode (when risk score > 60). It monitors all production LAN traffic flowing through the server room Ethernet switch (via Pi3b's eth0 uplink). Alerts are published to `sentinel/ids`.
- **AC600** creates a WiFi access point named `SENTINEL-SECURE`. Operator connects their laptop to this network to access the dashboard. dnsmasq assigns IPs in the 192.168.50.0/24 range. Pi3b routes between the WiFi subnet and the wired LAN, allowing the operator to access the dashboard at `http://192.168.100.1:8080` through the WiFi connection. Firewall rules on Pi3b restrict WiFi clients to only port 8080 on Pi4 — no other production LAN services are reachable from the WiFi network.
- **Dashboard Aggregator** subscribes to all `sentinel/+` topics and serves the data via REST API on port 8080. This API is used by external tools and as a fallback. The primary dashboard connects directly to MQTT via WebSocket (port 9001) for real-time push updates.

---

## 7. Network Topology

### 7.1 Dual-Network Design

ULTRON operates on two physically separated networks:

| Network | Purpose | Subnet | Interface |
|---------|---------|--------|-----------|
| **Wired LAN** (Production) | Server monitoring, scanning, IDS | 192.168.100.0/24 | Pi eth0 → 5-port switch → server room |
| **WiFi Hotspot** (Management) | Operator dashboard access | 192.168.50.0/24 | Pi3b AC600 → operator laptop |

**Wired LAN assignments (production monitoring):**

| Device | IP | Connection | Purpose |
|--------|-----|-----------|---------|
| Pi4 | 192.168.100.1 | Ethernet → switch → server LAN | Scans production servers |
| Pi3a | 192.168.100.2 | Ethernet → switch → server LAN | Cowrie honeypot on production network |
| Pi3b | 192.168.100.3 | Ethernet → switch → server LAN | Suricata monitors production traffic |
| Server 1 | 192.168.100.10 | Server room LAN | Scanned by nmap/Nuclei |
| Server 2 | 192.168.100.20 | Server room LAN | Scanned by nmap/Nuclei |
| Server N | 192.168.100.x | Server room LAN | Scanned by nmap/Nuclei |

**WiFi hotspot assignments (management only):**

| Device | IP | Connection | Purpose |
|--------|-----|-----------|---------|
| Pi3b AC600 | 192.168.50.1 | WiFi AP (SENTINEL-SECURE) | DHCP + DNS for management |
| Operator Laptop | 192.168.50.10-50 | WiFi client | Dashboard access |

### 7.2 MQTT Broker Configuration

Mosquitto runs on Pi4 as the central message broker. All inter-node communication flows through it.

**Broker Properties:**
- Protocol: MQTT v3.1.1
- Persistence: Enabled (messages survive broker restart)
- Max connections: 20
- Max in-flight messages: 200
- Max queued messages: 1000
- Message size limit: 64KB
- Keep-alive timeout: 60 seconds

**Authentication:** 7 service accounts with unique credentials:

| Username | Password | Node | Purpose |
|----------|----------|------|---------|
| pi4-core | (auto-generated) | Pi4 | Risk engine, scanner, self-healer |
| pi3a-canary | (auto-generated) | Pi3a | Canary bridge, web lure |
| pi3b-ids | (auto-generated) | Pi3b | Suricata, aggregator |
| pi3b-ap | (auto-generated) | Pi3b | WiFi AP management |
| dashboard | (auto-generated) | Pi4 | Dashboard WebSocket |
| esp32-c3 | (auto-generated) | ESP32-C3 | LED commands, status |
| esp32-wroom | (auto-generated) | ESP32-WROOM | Tripwire, portal |

### 7.3 Topic Hierarchy

```
sentinel/
├── mode                    # System mode (ULTRON or LAB)
├── risk/
│   ├── current             # Current risk score + band
│   └── history             # Historical scores (last 1000)
├── alert/
│   ├── active              # Currently active alerts
│   └── history             # Resolved alerts
├── canary/
│   ├── ssh                 # SSH honeypot events (Cowrie)
│   ├── web                 # Web lure events
│   └── file                # Canary file access (auditd)
├── scan/
│   ├── nmap                # Port scan results
│   ├── nuclei              # Vulnerability scan results
│   └── lynis               # System audit results
├── ids/
│   ├── suricata            # IDS alert events
│   └── wireless            # Wireless anomaly events
├── tripwire/
│   ├── pi3a                # Pi3a enclosure sensor
│   └── pi3b                # Pi3b enclosure sensor
├── selfheal/
│   ├── action              # Remediation actions taken
│   └── status              # Self-healer health
├── heartbeat/
│   ├── pi4                 # Pi4 health metrics
│   ├── pi3a                # Pi3a health metrics
│   └── pi3b                # Pi3b health metrics
├── led/
│   └── command             # LED color/animation commands
├── evidence/
│   └── sync                # Evidence synchronization events
└── status/
    └── system              # Overall system status
```

### 7.4 Quality of Service Levels

| Topic Category | QoS | Rationale |
|---------------|-----|-----------|
| `sentinel/risk/current` | 1 | Risk score must be delivered at least once |
| `sentinel/alert/active` | 2 | Alerts must be delivered exactly once (no duplicates, no misses) |
| `sentinel/tripwire/*` | 2 | Physical security events are critical |
| `sentinel/canary/*` | 1 | Canary events are important but occasional loss is acceptable |
| `sentinel/ids/*` | 1 | IDS alerts important but not mission-critical per event |
| `sentinel/scan/*` | 0 | Scan results are large; occasional loss acceptable (rescans) |
| `sentinel/heartbeat/*` | 0 | Heartbeats are frequent; occasional loss acceptable |
| `sentinel/led/command` | 0 | LED updates are frequent; latest value matters, not history |
| `sentinel/mode` | 2 | Mode changes must reach all nodes exactly once |

---

## 8. Risk Scoring Engine

### 8.1 Formula

The risk engine computes a single 0–100 score from six independent signal sources:

```
Risk Score = clamp(0, 100,
    S_canary    × W_canary    +
    S_rule      × W_rule      +
    S_scan      × W_scan      +
    S_ids       × W_ids       +
    S_tripwire  × W_tripwire  +
    S_behavior  × W_behavior
)
```

### 8.2 Component Weights

| Component | Weight (W) | Max Contribution | Signal Source | Decay Rate |
|-----------|-----------|-----------------|---------------|------------|
| Canary events | 0.25 | 25 | Pi3a honeypot + file access | 2 pts/10s |
| Rule alerts | 0.20 | 20 | Suricata IDS signatures | 2 pts/10s |
| Scanner findings | 0.15 | 15 | nmap/Nuclei/Lynis results | 2 pts/10s |
| IDS alerts | 0.15 | 15 | Suricata + wireless anomalies | 2 pts/10s |
| Tripwire | 0.15 | 15 | ESP32-WROOM GPIO sensors | 2 pts/10s |
| Behavioral | 0.10 | 10 | Unusual traffic patterns | 2 pts/10s |

**Why these weights?**
- Canary events (0.25): Highest weight because they indicate direct attacker interaction with the system. An attacker accessing fake credentials or executing commands in the honeypot is the strongest signal of compromise.
- Rule alerts (0.20): Suricata signatures are deterministic and high-confidence. Known attack patterns are reliable indicators.
- Scanner findings (0.15): Vulnerability scan results indicate exposure but not active exploitation.
- IDS alerts (0.15): Network-based detection catches lateral movement and scanning.
- Tripwire (0.15): Physical tampering is the highest-severity event but rarest.
- Behavioral (0.10): Statistical anomalies are useful but prone to false positives.

### 8.3 Risk Bands

| Band | Range | Color | LED Animation | Response |
|------|-------|-------|---------------|----------|
| GREEN | 0–29 | Green | Breathing (slow pulse) | Normal monitoring. No action. |
| YELLOW | 30–59 | Yellow | Chasing (sequential LEDs) | Increase scan frequency. Enable detailed logging. |
| RED | 60–84 | Red | Strobe (fast flash) | Activate IPS mode. Block IPs. Email alert. |
| PURPLE | 85–100 | Purple | Pulsing + sparkle | Full quarantine. Tripwire buzzer. All ports blocked. |

### 8.4 Decay Logic

Risk scores decay over time to prevent transient events from permanently locking the system:

```
Every 10 seconds:
    if current_score > 0:
        current_score = current_score - 2
    if current_score < 0:
        current_score = 0

    if current_score != previous_band:
        publish new risk band
        update LED color
```

**Decay behavior:**
- A single canary event adds 25 points (max contribution)
- At 2 pts/10s decay, it takes 125 seconds (~2 minutes) to decay to zero
- Multiple events compound: 3 canary events in rapid succession → 75 points (RED zone)
- The system naturally returns to GREEN after the threat passes

### 8.5 Alert Generation

Alerts are generated when:

| Condition | Alert Level | Action |
|-----------|------------|--------|
| Score crosses 30 (GREEN→YELLOW) | WARNING | Log event, increase logging |
| Score crosses 60 (YELLOW→RED) | CRITICAL | Email alert, activate IPS |
| Score crosses 85 (RED→PURPLE) | EMERGENCY | Email + tripwire buzzer + quarantine |
| Score drops below 60 (RED→YELLOW) | RESOLVED | Email "all clear" |
| Score drops below 30 (YELLOW→GREEN) | RESOLVED | Email "all clear" |
| Tripwire triggers | EMERGENCY | Immediate email + buzzer + LED |
| Self-healing action taken | INFO | Log action, publish to dashboard |
| Scan completes | INFO | Publish results, update score |

---

## 9. Scanner Engine

### 9.1 Scan Types

The scanner runs on Pi4 and targets **production servers on the wired LAN** (192.168.100.0/24). It connects to the server room via the 5-port Ethernet switch.

| Scanner | Purpose | Frequency | Duration | Output |
|---------|---------|-----------|----------|--------|
| nmap | Port discovery + service detection on LAN servers | Every 15 min | ~2 min | Open ports, service versions |
| Nuclei | Vulnerability template matching against LAN servers | Every 15 min (staggered) | ~5 min | CVEs, misconfigurations |
| Lynis | System security audit (ULTRON self-audit) | Every 6 hours | ~3 min | Hardening score, recommendations |

### 9.2 Scan Scheduling

Scans run on systemd timers, not continuous processes:

```
scanner-nmap.timer     → triggers scanner-nmap.service     → every 15 minutes
scanner-nuclei.timer   → triggers scanner-nuclei.service   → every 15 minutes (offset +5min)
scanner-lynis.timer    → triggers scanner-lynis.service    → every 6 hours
```

The offset between nmap and nuclei prevents resource contention. Both scanners run sequentially (nmap first, then nuclei) to avoid network saturation.

### 9.3 Result Processing

Each scan produces structured output that is parsed and published to MQTT:

**nmap results → `sentinel/scan/nmap`:**
- Open ports per production server (192.168.100.x)
- Service versions detected on each server
- OS fingerprint of each server
- Ports that changed since last scan (new exposure or closure delta)

**Nuclei results → `sentinel/scan/nuclei`:**
- Vulnerability ID (CVE number)
- Severity (critical/high/medium/low/info)
- Affected host + port
- Template URL for remediation reference

**Lynis results → `sentinel/scan/lynis`:**
- Overall hardening score (0–100)
- Failed tests (specific misconfigurations)
- Recommendations (with remediation commands)

### 9.4 Scan-to-Score Integration

Scanner findings feed directly into the risk score:

| Finding Type | Score Addition | Rationale |
|-------------|---------------|-----------|
| New open port | +5 per port | Unexpected service exposure |
| Known CVE (critical) | +15 | Actively exploitable vulnerability |
| Known CVE (high) | +10 | Significant security weakness |
| Known CVE (medium) | +5 | Moderate risk |
| Lynis hardening < 60 | +10 | System not properly hardened |
| Lynis hardening < 40 | +15 | Severely misconfigured system |

---

## 10. Deception Layer

### 10.1 Canary Strategy

ULTRON uses a multi-vector deception strategy to detect unauthorized access:

**SSH Honeypot (Cowrie):**
- Runs on Pi3a on port 22
- Accepts any username/password combination
- Logs every command executed by the attacker
- Simulates a realistic Linux filesystem
- Records uploaded/downloaded files
- Publishes events to `sentinel/canary/ssh`

**Canary Files:**
- Placed in `/home/admin/` on Pi3a
- Files: `creds.txt`, `id_rsa`, `passwords.txt`, `backup.sql`
- All files contain obviously fake credentials (honeytokens)
- Monitored by auditd — any read/copy triggers an alert
- Published to `sentinel/canary/file`

**Web Lure:**
- Fake admin login page served on port 80 (Pi3a)
- Looks like a WordPress/PHP admin panel
- Any form submission is logged and published to `sentinel/canary/web`
- Includes hidden tracking pixels for email harvesting

### 10.2 Detection Confidence

| Deception Vector | Confidence | False Positive Rate | Detection Speed |
|-----------------|-----------|---------------------|-----------------|
| Cowrie command execution | High (95%) | Very low | Instant (on command) |
| Canary file read | Very high (99%) | Near zero | Instant (on access) |
| Web lure form submit | Medium (70%) | Low | Instant (on submit) |
| Cowrie login attempt | Low (30%) | High (scanners) | Instant (on login) |

The confidence score is used in the risk calculation. High-confidence events (canary file access, honeypot command execution) contribute more to the risk score than low-confidence events (SSH login attempts, which could be automated scanners).

### 10.3 Canary Bridge Logic

The canary bridge on Pi3a processes two log streams:

**Stream 1 — Cowrie JSON log:**
```
For each log entry:
    Extract: timestamp, src_ip, username, command, success
    Classify: login_attempt | command_execution | file_transfer
    If command_execution:
        confidence = 0.95
        score_contribution = 20
    If login_attempt:
        confidence = 0.30
        score_contribution = 5
    Publish to sentinel/canary/ssh
```

**Stream 2 — Auditd log:**
```
For each log entry:
    Extract: timestamp, pid, uid, filename, syscall (read/open)
    If filename in canary_list (creds.txt, id_rsa, etc.):
        confidence = 0.99
        score_contribution = 25
    Publish to sentinel/canary/file
```

---

## 11. Wireless Attacks & IDS

### 11.1 Monitor Mode (TL-WN722N)

The TL-WN722N adapter on Pi3a supports monitor mode and packet injection for wireless security assessment.

**Capabilities:**
- Passive packet capture on all WiFi channels
- Deauthentication testing (LAB mode only)
- Evil twin access point creation (LAB mode only)
- WiFi handshake capture for offline cracking (LAB mode only)

**ULTRON mode:** Monitor mode only. Captures beacon frames and probe requests to detect unauthorized access points. No active attacks.

**LAB mode:** Full attack capability. Students can practice:
- WiFi deauthentication attacks
- Evil twin AP creation
- Handshake capture and offline cracking
- WPA2 password auditing

### 11.2 Suricata IDS/IPS

Suricata runs on Pi3b, monitoring all production LAN traffic on the wired Ethernet uplink (eth0) via AF_PACKET. This means every packet flowing between production servers in the server room is inspected.

**Detection Rules:**
- ET Open Ruleset (Emerging Threats) — 30,000+ rules
- Custom ULTRON rules for:
  - Canary file access attempts from outside the honeypot
  - Unusual SSH connection patterns
  - Port scanning behavior
  - Known malware C2 communication patterns

**Operating Modes:**
- **IDS mode (default, GREEN/YELLOW):** Monitors traffic and generates alerts. No blocking.
- **IPS mode (RED):** Monitors + blocks. Drops packets matching high-severity rules. Adds blocking rules via nftables.

**Performance on Pi3b:**
- RAM usage: ~150MB (of 1GB available)
- CPU usage: ~25% at 100Mbps traffic
- Alert throughput: ~500 alerts/second
- Packet loss: <1% at 100Mbps

---

## 12. Self-Healing Framework

### 12.1 Architecture

The self-healing engine uses a **detector → evaluator → executor → verifier** pipeline:

```
DETECT → EVALUATE → DECIDE → EXECUTE → VERIFY → LOG
```

**DETECT:** TOML-defined detectors check system state every 60 seconds. Each detector queries a specific aspect of the system (SSH config, open ports, firewall rules, service status, disk space, TLS certificates).

**EVALUATE:** Each detector returns a status: `healthy`, `degraded`, or `critical`. The status includes the specific finding and the recommended remediation template.

**DECIDE:** The engine checks:
- Is the system in ULTRON mode? (Auto-fix only in ULTRON)
- Is the circuit breaker open? (Too many recent failures → pause)
- Is this specific check in the auto-fix whitelist? (Some checks are monitor-only)

**EXECUTE:** If approved, the engine applies the remediation template:
1. Take a snapshot of current state (for rollback)
2. Apply the fix (restart service, modify config, add firewall rule)
3. Wait for the change to take effect (5-second pause)

**VERIFY:** Re-run the detector to confirm the fix worked:
- If the check passes → mark as resolved, publish success
- If the check fails → roll back the change, publish failure, increment circuit breaker

**LOG:** All actions are logged to SQLite with timestamps, before/after state, and outcome.

### 12.2 Remediation Templates

Each template defines: what to check, how to fix it, and how to verify the fix.

| Template | Check | Fix | Verify |
|----------|-------|-----|--------|
| ssh_password_auth | `/etc/ssh/sshd_config` has `PasswordAuthentication yes` | Set `PasswordAuthentication no`, restart sshd | Re-check config file |
| open_port_unexpected | nmap finds port not in whitelist | Add nftables drop rule for that port | Re-scan confirms port closed |
| cowrie_stopped | Cowrie systemd unit not active | Restart Cowrie service | Unit status = active |
| disk_usage_high | Disk usage > 85% | Rotate logs, delete old evidence | Disk usage < 70% |
| tls_cert_expired | Certificate expiry < 7 days | Run certbot renewal | Re-check expiry date |
| firewall_disabled | nftables chain missing or policy accept | Restore sentinel chain, set policy drop | Chain exists, policy drop |
| ntp_drift | System clock drift > 5 seconds | Restart chrony service | Drift < 1 second |

### 12.3 Circuit Breaker

The circuit breaker prevents the self-healing engine from entering a failure loop:

```
State: CLOSED (normal) → OPEN (halted) → HALF-OPEN (testing)

Transition logic:
- CLOSED: Every failure increments counter
- If counter >= 3 in 5 minutes → OPEN
- OPEN: No remediation actions for 10 minutes
- After 10 minutes → HALF-OPEN
- HALF-OPEN: Allow one remediation attempt
  - If success → CLOSED, reset counter
  - If failure → OPEN, wait 10 minutes
```

---

## 13. Alert & Reporting

### 13.1 Email Alerts

ULTRON sends email alerts through a configurable SMTP connection.

**Alert triggers:**
- Risk band change (any transition between GREEN/YELLOW/RED/PURPLE)
- Tripwire activation
- Self-healing action taken
- Scan completion with critical findings
- System health warnings (disk full, service down, clock drift)

**Email format:**
- Subject: `[ULTRON] {severity} — {alert_type}`
- Body: Structured text with timestamp, current risk score, affected component, action taken
- HTML version: Includes risk score gauge, event timeline, affected services

### 13.2 Reports

ULTRON generates Markdown (.md) reports stored on the evidence pendrive:

| Report Type | Frequency | Contents |
|-------------|-----------|----------|
| Daily summary | 24 hours | All events, risk score timeline, scans, alerts |
| Weekly executive | 7 days | Top threats, remediation actions, hardening score trend |
| Incident report | On-demand | Full timeline of a specific incident with evidence |
| Scan report | Per scan | nmap/Nuclei/Lynis results with remediation guidance |

Reports are generated by the evidence manager service and synced to the 128GB pendrive via rsync.

---

## 14. Dashboard

### 14.1 Architecture

The dashboard is a **single HTML file** served from Pi4 on port 8080. It uses no frameworks, no build tools, no npm packages. Pure HTML + CSS + vanilla JavaScript.

**Data source:** WebSocket connection to Mosquitto broker (port 9001). The dashboard subscribes to `sentinel/risk/current`, `sentinel/alert/active`, `sentinel/scan/#`, `sentinel/selfheal/action`, and `sentinel/status/system`.

### 14.2 Panel Layout

```
┌─────────────────────────────────────────────────┐
│                 ULTRON DASHBOARD                  │
├──────────┬──────────┬──────────┬─────────────────┤
│ RISK     │ BAND     │ NODE     │ MODE            │
│ SCORE    │ COLOR    │ STATUS   │ ULTRON / LAB    │
│ (gauge)  │ (green/  │ (3 nodes │                 │
│          │ yellow/  │ up/down) │                 │
│          │ red/     │          │                 │
│          │ purple)  │          │                 │
├──────────┴──────────┴──────────┴─────────────────┤
│              ACTIVE ALERTS                        │
│ (scrollable list: severity, message, time)        │
├──────────────────────────────────────────────────┤
│         RECENT SCANS                              │
│ (nmap: open ports | Nuclei: CVEs | Lynis: score) │
├──────────────────────────────────────────────────┤
│         SELF-HEALING LOG                          │
│ (action taken, result, timestamp)                 │
├──────────────────────────────────────────────────┤
│         RISK HISTORY (24h chart)                  │
│ (line chart: score over time, color-coded bands) │
└──────────────────────────────────────────────────┘
```

### 14.3 Real-Time Updates

The dashboard uses WebSocket to receive live MQTT messages. When a new event arrives:

1. Parse the MQTT payload (JSON)
2. Update the relevant panel (risk score, alert list, scan results)
3. If risk band changed, update the color theme of the entire dashboard
4. Animate transitions (smooth color changes, alert slide-in)

The dashboard also provides a "manual scan" button (LAB mode only) that triggers an on-demand nmap scan via MQTT publish to `sentinel/scan/trigger`.

---

## 15. ESP32 Physical Layer

### 15.1 ESP32-C3 — Threat Light + Status Display

**Connection:** USB to Pi4 (via USB Hub)
**Components:** WS2812B NeoPixel ring (8 LEDs) + SSD1306 OLED (128×64)

**NeoPixel LED behavior by risk band:**

| Risk Band | Color | Animation | Description |
|-----------|-------|-----------|-------------|
| GREEN | Green | Breathing | Slow pulse (2s cycle), all LEDs synchronized |
| YELLOW | Yellow | Chasing | Sequential LEDs light up in a circle (500ms delay) |
| RED | Red | Strobe | Fast flash (100ms on/off), all LEDs synchronized |
| PURPLE | Purple | Pulsing + sparkle | Slow pulse (1.5s) with random sparkle effects |

**OLED display content:**
```
┌────────────────────────┐
│  ULTRON v1.0           │
│  Risk: 42  [YELLOW]    │
│  Mode: ULTRON          │
│  Nodes: 3/3 online     │
│  Scan: 12m ago         │
│  Alerts: 2 active      │
└────────────────────────┘
```

**Serial protocol (Pi4 → ESP32-C3):**
- `LED:<color>` — Set LED color (green, yellow, red, purple, blue, off)
- `OLED:<line1>:<line2>:<line3>` — Update OLED display
- `PING` — Health check (responds with `PONG`)
- `STATUS` — Returns current LED color and WiFi status
- `REBOOT` — Software reset

### 15.2 ESP32-WROOM — Tripwire + Portal + Debug

**Connections:**
- GPIO16 ← Pi3a GPIO17 (tripwire sensor, honeypot enclosure)
- GPIO17 ← Pi3b GPIO27 (tripwire sensor, Pi3b enclosure)
- USB ← Pi4 Hub Port 2 (power + serial data)
- GPIO4 → Passive buzzer (tripwire alarm)

**Tripwire logic:**
```
Every 100ms:
    Read GPIO16 (Pi3a sensor)
    Read GPIO17 (Pi3b sensor)
    
    If GPIO16 == LOW (pulled down = wire cut or enclosure opened):
        Sound buzzer for 2 seconds
        Publish: sentinel/tripwire/pi3a {triggered: true, timestamp: now}
        Update: OLED shows "TRIPWIRE: PI3a BREACH"
    
    If GPIO17 == LOW:
        Sound buzzer for 2 seconds
        Publish: sentinel/tripwire/pi3b {triggered: true, timestamp: now}
        Update: OLED shows "TRIPWIRE: PI3b BREACH"
```

**WiFi Portal:**
- Creates an open WiFi network named `SENTINEL-DEBUG`
- Serves a captive portal page showing:
  - Current system status (fetched from Pi4 via MQTT)
  - Tripwire sensor status
  - Node health metrics
  - Quick-action buttons (for LAB mode: start scan, view leaderboard)

**Debug Server:**
- HTTP server on port 80
- Endpoints:
  - `GET /status` — JSON: WiFi config, tripwire states, uptime
  - `GET /config` — JSON: current WiFi SSID, password, Pi4 IP
  - `POST /config` — Update WiFi credentials or Pi4 IP
  - `POST /reboot` — Software reset

---

## 16. Operating Modes

### 16.1 ULTRON Mode (Full Protection)

In ULTRON mode, all services operate autonomously:

| Service | Behavior |
|---------|----------|
| Scanner | Automatic 15-minute scan cycles |
| Risk Engine | Continuous scoring from all sources |
| Self-Healer | Auto-remediation of fixable issues |
| Suricata | IDS mode (default), IPS mode when score > 60 |
| Canary Bridge | Active monitoring of honeypot + canary files |
| Alerts | Email notifications for critical events |
| Dashboard | Real-time updates, no manual scan button |
| ESP32 LED | Shows live risk band color |
| TL-WN722N | Monitor mode only (passive packet capture) |

**ULTRON mode is the default.** The system boots into ULTRON mode unless explicitly configured for LAB.

### 16.2 LAB Mode (CTF Training)

In LAB mode, the system becomes a training platform:

| Service | Behavior |
|---------|----------|
| Scanner | Manual only (students trigger via dashboard or CLI) |
| Risk Engine | Still scores, but auto-response disabled |
| Self-Healer | Monitor-only (logs issues, no auto-fix) |
| Suricata | IDS mode only (never IPS) |
| Canary Bridge | Active (students can interact with honeypot) |
| Alerts | Dashboard only (no email) |
| Dashboard | Shows leaderboard, manual scan buttons, challenge progress |
| ESP32 LED | Shows risk band, but no auto-quarantine |
| TL-WN722N | Full attack capability (deauth, evil twin, handshake capture) |

**Mode transition:**
```
Switch from ULTRON to LAB:
    Stop scanner timer
    Disable self-healer auto-fix
    Disable Suricata IPS mode
    Enable TL-WN722N attack interfaces
    Update dashboard to show leaderboard
    Publish: sentinel/mode {mode: "LAB", timestamp: now}

Switch from LAB to ULTRON:
    Start scanner timer
    Enable self-healer auto-fix
    Enable Suricata IPS mode
    Disable TL-WN722N attack interfaces
    Update dashboard to show monitoring view
    Publish: sentinel/mode {mode: "ULTRON", timestamp: now}
```

---

## 17. LAB / CTF Mode

### 17.1 Student Journey

**Step 1 — Connect:**
Student connects laptop to `SENTINEL-SECURE` WiFi (created by Pi3b's AC600). Opens browser to `http://192.168.100.1:8080`. Dashboard shows LAB mode with leaderboard and available challenges.

**Step 2 — Register:**
Student enters a username on the dashboard. This creates a leaderboard entry. All subsequent actions are attributed to this username.

**Step 3 — Choose Challenge:**

| Challenge | Difficulty | Points | Skill Tested |
|-----------|-----------|--------|-------------|
| Port Scan | Easy | 10 | nmap basics, service enumeration |
| Vuln Hunt | Medium | 25 | Nuclei template matching, CVE identification |
| System Audit | Medium | 25 | Lynis hardening, configuration review |
| WiFi Recon | Hard | 50 | Monitor mode, packet analysis, SSID discovery |
| Honeypot Escape | Hard | 50 | Cowrie interaction, canary file discovery |
| Full Compromise | Expert | 100 | Combines all skills: scan → find vuln → exploit → cover tracks |
| Self-Heal Bypass | Expert | 100 | Modify system state to trigger self-healing, then verify fix |

**Step 4 — Execute:**
Student performs the challenge using their own tools (nmap, nuclei, hydra, aircrack-ng, etc.) against the ULTRON system. The system detects and logs all activity.

**Step 5 — Score:**
Points are awarded when:
- The student's action is detected by ULTRON (proves the detection works)
- The student provides evidence (screenshot, log excerpt) of the finding
- The student explains the remediation (how to fix the issue)

**Step 6 — Leaderboard:**
Dashboard shows a real-time leaderboard:
```
┌─────────────────────────────────────────┐
│           CTF LEADERBOARD                │
├──────┬──────────────┬──────┬────────────┤
│ Rank │ Student      │ Score│ Challenges │
├──────┼──────────────┼──────┼────────────┤
│ 1    │ security_ninja│ 275  │ 6/7        │
│ 2    │ hackerman     │ 200  │ 5/7        │
│ 3    │ cyber_panda   │ 150  │ 4/7        │
└──────┴──────────────┴──────┴────────────┘
```

### 17.2 Learning Objectives

After completing all challenges, students will have practical experience with:
- Network reconnaissance and port scanning
- Vulnerability assessment and CVE identification
- System hardening and security auditing
- Wireless security testing
- Honeypot interaction and deception awareness
- Self-healing system concepts
- Risk scoring and threat prioritization

---

## 18. MQTT Schema Reference

### 18.1 Message Format

All MQTT payloads are JSON with a standard envelope:

```json
{
    "timestamp": "2027-03-01T10:30:00Z",
    "source": "pi3a-canary",
    "type": "canary_ssh",
    "severity": "warning",
    "data": { ... }
}
```

### 18.2 Topic Payloads

| Topic | QoS | Payload Fields |
|-------|-----|----------------|
| `sentinel/risk/current` | 1 | `score` (int), `band` (string), `components` (object with 6 scores), `timestamp` |
| `sentinel/alert/active` | 2 | `alert_id` (UUID), `severity` (info/warning/critical/emergency), `message` (string), `source` (string), `action_taken` (string), `timestamp` |
| `sentinel/canary/ssh` | 1 | `src_ip` (string), `username` (string), `command` (string), `success` (bool), `confidence` (float) |
| `sentinel/canary/file` | 1 | `filename` (string), `syscall` (string), `pid` (int), `uid` (int), `confidence` (float) |
| `sentinel/canary/web` | 1 | `src_ip` (string), `form_data` (object), `user_agent` (string) |
| `sentinel/scan/nmap` | 0 | `hosts` (array), `open_ports` (array), `changed_since_last` (array) |
| `sentinel/scan/nuclei` | 0 | `vulnerabilities` (array: id, severity, host, port, template) |
| `sentinel/scan/lynis` | 0 | `hardening_score` (int), `failed_tests` (array), `recommendations` (array) |
| `sentinel/ids/suricata` | 1 | `signature` (string), `src_ip` (string), `dst_ip` (string), `severity` (int), `protocol` (string) |
| `sentinel/tripwire/pi3a` | 2 | `triggered` (bool), `gpio` (int), `timestamp` |
| `sentinel/tripwire/pi3b` | 2 | `triggered` (bool), `gpio` (int), `timestamp` |
| `sentinel/selfheal/action` | 1 | `template` (string), `action` (string), `result` (success/failure/rollback), `before` (object), `after` (object) |
| `sentinel/heartbeat/*` | 0 | `uptime` (int), `cpu_percent` (float), `memory_percent` (float), `disk_percent` (float), `services` (array) |
| `sentinel/led/command` | 0 | `color` (string), `animation` (string), `source` (string) |
| `sentinel/mode` | 2 | `mode` (ULTRON/LAB), `timestamp`, `initiator` (string) |
| `sentinel/evidence/sync` | 1 | `files_synced` (int), `bytes_transferred` (int), `destination` (string) |
| `sentinel/status/system` | 0 | `nodes_online` (int), `mode` (string), `risk_band` (string), `last_scan` (timestamp) |

---

## 19. Systemd Services Map

### 19.1 Pi4 Brain — Services

| Service | Type | Starts After | Restart Policy |
|---------|------|-------------|----------------|
| mosquitto.service | always | network-online | always (5s delay) |
| sentinel-risk.service | always | mosquitto | always (10s delay) |
| sentinel-scanner.service | timer | network-online | on-failure |
| sentinel-selfheal.service | always | mosquitto | always (10s delay) |
| sentinel-alert.service | always | mosquitto | always (10s delay) |
| sentinel-dashboard.service | always | network-online | always (5s delay) |
| sentinel-evidence.service | timer | network-online | on-failure |

**Boot order dependency chain:**
```
network-online.target
    └── mosquitto.service
        ├── sentinel-risk.service
        ├── sentinel-selfheal.service
        └── sentinel-alert.service
    └── sentinel-dashboard.service
    └── sentinel-scanner.timer
    └── sentinel-evidence.timer
```

### 19.2 Pi3a Attack — Services

| Service | Type | Starts After | Restart Policy |
|---------|------|-------------|----------------|
| cowrie.service | always | network-online | always (10s delay) |
| sentinel-canary.service | always | network-online | always (10s delay) |
| sentinel-lure.service | always | network-online | always (5s delay) |
| auditd.service | always | systemd-journald | always |

### 19.3 Pi3b IDS & Gateway — Services

| Service | Type | Starts After | Restart Policy |
|---------|------|-------------|----------------|
| suricata.service | always | network-online | always (10s delay) |
| sentinel-aggregator.service | always | network-online | always (10s delay) |
| hostapd.service | always | network-online | always (5s delay) |
| dnsmasq.service | always | network-online | always (5s delay) |

### 19.4 Service Hardening

All systemd services include security hardening directives:

```
[Service]
# File system isolation
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/sentinel /var/log/sentinel /etc/sentinel

# Network isolation
PrivateNetwork=no
RestrictAddressFamilies=AF_INET AF_UNIX

# Capability restrictions
CapabilityBoundingSet=
NoNewPrivileges=yes

# Resource limits
MemoryMax=256M
CPUQuota=80%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=sentinel-<service>
```

---

## 20. Security Hardening

### 20.1 Credential Management

| Credential | Storage | Rotation |
|-----------|---------|----------|
| MQTT passwords | `/etc/mosquitto/passwd` | Manual (during setup) |
| SSH keys | `~/.ssh/authorized_keys` | Manual |
| WiFi AP password | hostapd.conf | Manual |
| SMTP credentials | `/etc/sentinel/smtp.conf` (chmod 600) | Manual |
| Database | SQLite (no auth needed) | N/A |

### 20.2 SSH Hardening

```
- Key-based authentication only (PasswordAuthentication no)
- Root login disabled (PermitRootLogin no)
- Rate limiting: MaxAuthTries 3, LoginGraceTime 30
- AllowUsers sentinel (restrict to service account)
- Protocol 2 only
- X11Forwarding disabled
- TCP forwarding disabled (unless explicitly needed)
```

### 20.3 Network Hardening

```
Firewall (nftables):
- Default policy: DROP (all incoming, all forwarded)
- Allow: SSH (22) from LAN only
- Allow: MQTT (1883) from LAN only
- Allow: Dashboard (8080) from WiFi subnet only
- Allow: HTTP (80) from WiFi subnet only (Pi3a lure)
- Allow: DNS (53) from WiFi subnet only (Pi3b dnsmasq)
- Allow: DHCP (67) from WiFi subnet only (Pi3b dnsmasq)
- Allow: ICMP ping from LAN
- Drop everything else
```

### 20.4 Wired LAN Hardening

```
Production LAN security:
- ULTRON nodes use static IPs only (no DHCP from production network)
- nftables DROP policy on all ULTRON nodes (only explicitly allowed traffic)
- Suricata IPS mode auto-blocks high-severity threats from production LAN
- Scanner targets are whitelisted (192.168.100.0/24 only)
- No ULTRON services expose ports to the production LAN (only outgoing scans)
- Pi3b monitors all production traffic for anomalies and intrusion attempts
- Evidence logs (Suricata alerts, scan results, canary events) stored on Pi4 SSD
- WiFi management network is completely isolated from production LAN
```

### 20.5 Physical Security

```
- Tripwire sensors on Pi3a and Pi3b enclosures
- ESP32-WROOM buzzer sounds on physical breach
- Dashboard shows tripwire status in real-time
- Email alert on tripwire activation
- SSD encrypted with LUKS (optional)
- Evidence pendrive encrypted with LUKS (optional)
```

### 20.6 Full Hardening Checklist

- [ ] All MQTT accounts have unique passwords
- [ ] SSH key-based auth only, password auth disabled
- [ ] nftables default policy DROP on all 3 nodes
- [ ] Wired LAN: no ULTRON services expose ports to production network
- [ ] WiFi management network isolated from production LAN
- [ ] Suricata IPS mode tested against production traffic
- [ ] All services run as unprivileged users
- [ ] systemd hardening applied to all services
- [ ] No credentials in source code or config files (except encrypted stores)
- [ ] Dashboard only accessible from WiFi subnet
- [ ] Suricata rules updated weekly
- [ ] Lynis audit score > 70 before deployment
- [ ] Tripwire sensors tested and functional
- [ ] Email alerts tested and working
- [ ] Evidence pendrive synced and verified
- [ ] Clock synchronized via NTP (chrony)
- [ ] Log rotation configured (max 100MB per service)
- [ ] Disk usage monitored (alert at 85%)

---

## 21. Demo Script

### 21.1 Setup (5 minutes before demo)

1. Power on ULTRON (connect power adapters)
2. Wait 90 seconds for all services to start
3. Verify LED is GREEN (risk score 0)
4. Connect operator laptop to `SENTINEL-SECURE` WiFi
5. Open `http://192.168.100.1:8080` in browser
6. Verify dashboard shows: 3/3 nodes online, GREEN band, ULTRON mode

### 21.2 Live Demo Flow (10 minutes)

| Time | Action | What Audience Sees |
|------|--------|-------------------|
| 0:00 | Introduce ULTRON | Dashboard on screen, GREEN LED breathing |
| 0:30 | Trigger canary access (SSH to Pi3a, cat creds.txt) | Score rises to 25. LED turns YELLOW. Alert appears on dashboard. |
| 1:30 | Show Cowrie honeypot interaction | Dashboard shows attacker commands logged in real-time |
| 2:30 | Trigger web lure (submit fake login) | Score rises further. New canary alert. |
| 3:30 | Run on-demand scan against LAN server (nmap 192.168.100.x) | Scan results appear on dashboard — open ports, services, vulnerabilities listed |
| 5:00 | Score crosses 60 → RED | LED turns RED strobe. IPS mode activates. Email alert sent. |
| 6:00 | Show Suricata detecting suspicious traffic on production LAN | IDS alert appears on dashboard with source IP and signature |
| 7:00 | Trigger tripwire (open Pi3a enclosure) | Buzzer sounds. PURPLE alert. Dashboard shows physical breach. |
| 8:00 | Show self-healing (if applicable) | Dashboard shows auto-remediation action + verification |
| 9:00 | Switch to LAB mode | Dashboard shows leaderboard. Demonstrate student scan against LAN target. |
| 10:00 | Summary | Highlight: $290 cost, zero cloud, plugs into any server room, autonomous 24/7 |

### 21.3 Backup Plans

| Issue | Backup |
|-------|--------|
| WiFi connection fails | Use Pi4's built-in Ethernet + USB keyboard/monitor |
| Dashboard doesn't load | Show MQTT messages directly via mosquitto_sub |
| LED doesn't respond | Point to dashboard risk score (same data) |
| Email alert not received | Show alert in dashboard (same information) |
| Scan takes too long | Pre-cached results from earlier run |

---

## 22. Arsenal Submission

### 22.1 Submission Fields

| Field | Content |
|-------|---------|
| **Tool Name** | ULTRON — Autonomous Cybersecurity Suite |
| **One-Line Description** | A $290 modular Raspberry Pi device that plugs into any server room's Ethernet switch and autonomously monitors, detects, attacks, scans, and heals — a complete SOC in a box with real-time LED threat visualization |
| **Category** | Blue Team & Detection |
| **Source Code** | https://github.com/[your-username]/ultron |
| **License** | MIT |
| **Presenter** | [Your Name] — [Your Title/Affiliation] |
| **Event** | Black Hat Asia 2027 Arsenal, Singapore |
| **Dates** | February 28 – March 3, 2027 |

### 22.2 Abstract (150 words)

> ULTRON is a fully autonomous cybersecurity appliance built on three Raspberry Pi nodes and two ESP32 microcontrollers, costing under $300 in hardware. Designed as a modular device that plugs into any server room's Ethernet switch, it immediately begins monitoring the production LAN for threats. It integrates network intrusion detection (Suricata), SSH honeypots (Cowrie), vulnerability scanning (nmap + Nuclei + Lynis against production servers), and automated self-healing into a single cohesive system driven by MQTT pub/sub messaging.
>
> A risk-scoring engine fuses signals from six detection layers into a 0–100 score that drives both software response (firewall rules, service restarts) and physical indicators (NeoPixel LED color, OLED status display, tripwire buzzer alerts). The system operates 24/7 without cloud connectivity or dedicated security staff.
>
> ULTRON features dual operating modes: ULTRON (full autonomous protection against real threats) and LAB (educational CTF training platform). The LAB mode transforms the appliance into a hands-on cybersecurity training environment where students perform real scans against LAN targets, crack real defenses, and earn leaderboard points.
>
> Built entirely with open-source tools and running on Raspberry Pi hardware, ULTRON demonstrates that enterprise-grade autonomous security is accessible to schools, small businesses, and community labs.

### 22.3 Audience Takeaways

1. **Feasibility:** Autonomous cybersecurity is achievable on $290 of hardware with no cloud dependency
2. **Architecture:** MQTT pub/sub enables clean separation of detection, scoring, and response layers
3. **Dual-Mode Design:** The same hardware serves as both a production security appliance and an educational CTF platform
4. **Physical Feedback:** LED and OLED provide instant, intuitive threat visualization without a screen
5. **Self-Healing:** Rule-based remediation with circuit breakers demonstrates autonomous recovery without AI

---

## 23. Implementation Roadmap

### 23.1 Week 1: Foundation

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Hardware assembly, OS flash, network config | 3 Pis booting, SSH accessible, static IPs |
| 2 | Mosquitto setup, password file, ACL | MQTT broker running, all nodes connecting |
| 3 | Pi4 core services skeleton (risk engine, scanner) | Services start, subscribe to MQTT |
| 4 | Pi3a Cowrie + auditd + canary bridge | Honeypot accepting SSH, canary events publishing |
| 5 | Pi3b Suricata + aggregator | IDS generating alerts, REST API serving data |
| 6 | ESP32-C3 NeoPixel + OLED firmware | LED responds to MQTT commands |
| 7 | ESP32-WROOM tripwire + portal | Tripwire events publishing, debug page accessible |

### 23.2 Week 2: Core Intelligence

| Day | Task | Deliverable |
|-----|------|-------------|
| 8 | Risk scoring engine (full formula + decay) | Score updates in real-time, bands working |
| 9 | Scanner integration (nmap + Nuclei + Lynis) | Automated scans running on timers |
| 10 | Self-healing engine + TOML templates | Auto-remediation working for 3+ templates |
| 11 | Alert system (email + HTML templates) | Email alerts sending on band changes |
| 12 | Dashboard (single HTML file + WebSocket) | Live dashboard showing all data |
| 13 | Evidence manager + pendrive sync | Reports generating, syncing to pendrive |
| 14 | Integration testing | Full pipeline: detect → score → respond → report |

### 23.3 Week 3: Polish & Security

| Day | Task | Deliverable |
|-----|------|-------------|
| 15 | Security hardening (nftables, SSH, systemd) | All hardening checklist items complete |
| 16 | Circuit breaker + rollback logic | Self-healer doesn't loop on failures |
| 17 | Mode switching (ULTRON ↔ LAB) | Both modes working, clean transition |
| 18 | LAB mode + leaderboard | CTF challenges defined, scoring working |
| 19 | WiFi AP + dnsmasq + captive portal | Operator can connect and access dashboard |
| 20 | Power management + boot ordering | System boots cleanly, services start in order |
| 21 | Full regression test | All 30+ test cases passing |

### 23.4 Week 4: Demo & Documentation

| Day | Task | Deliverable |
|-----|------|-------------|
| 22 | Demo script rehearsal | 10-minute demo running smoothly |
| 23 | Backup plan testing | All 5 backup scenarios verified |
| 24 | blackhat.md final review | Document complete, no contradictions |
| 25 | Video demo recording | 3-minute demo video for submission |
| 26 | Arsenal submission package | All fields complete, GitHub repo public |
| 27 | Final hardware check | All components verified, spare parts packed |
| 28 | Submit to Black Hat Asia 2027 | Submission complete |

---

## 24. Testing Strategy

### 24.1 Unit Tests

| Component | Test Case | Expected Result |
|-----------|-----------|----------------|
| Risk Engine | Score = 0 when no events | GREEN band, score 0 |
| Risk Engine | Single canary event adds 25 | Score = 25, GREEN band |
| Risk Engine | 3 canary events rapidly | Score = 75, RED band |
| Risk Engine | Score decays by 2 per 10s | After 60s, score drops 12 points |
| Risk Engine | Score never exceeds 100 | clamp(0, 100, 150) = 100 |
| Risk Engine | Score never goes below 0 | clamp(0, 100, -10) = 0 |
| Self-Healer | Circuit breaker opens after 3 failures | No actions for 10 minutes |
| Self-Healer | Circuit breaker closes after success | Resume normal operations |

### 24.2 Integration Tests

| Test Case | Setup | Expected Result |
|-----------|-------|----------------|
| Canary → Score → LED | SSH to Pi3a, cat creds.txt | LED changes from GREEN to YELLOW |
| Scan → Score → Alert | Trigger nmap scan against 192.168.100.x (production server) | Scan results appear on dashboard with open ports and services |
| Suricata → Score → Alert | Generate suspicious traffic on production LAN | IDS alert appears on dashboard with source IP and signature |
| Tripwire → Score → Email | Open Pi3a enclosure | Email alert received within 30s |
| Self-Heal → Verify | Stop Cowrie service | Cowrie restarts, event logged |
| Mode Switch | Switch to LAB | Scanner stops, leaderboard appears |
| Dashboard → MQTT → LED | Click "Set LED Purple" on dashboard | ESP32-C3 LEDs turn purple |
| LAN Server Discovery | Run nmap 192.168.100.0/24 | Dashboard shows discovered production servers and their open ports |

### 24.3 Hardware Validation

| Test | Method | Pass Criteria |
|------|--------|---------------|
| Power budget | Measure current per adapter with multimeter | Each adapter within rated capacity (Pi4 < 3A, Pi3a < 2.5A, Pi3b < 2.5A) |
| Heat management | Run 24h stress test | Pi4 temp < 70°C |
| WiFi range | Walk with laptop, measure RSSI | Dashboard accessible at 30m |
| Tripwire sensitivity | Test with 100 open/close cycles | Zero missed triggers |
| LED brightness | Visual check in dark room | All 4 colors clearly distinguishable |
| Boot time | Time from power-on to GREEN LED | < 90 seconds |
| Evidence sync | Verify pendrive contents | All reports present and readable |

---

## 26. ULTRON-X: NVIDIA Jetson Nano Variant

### 26.1 Executive Summary

ULTRON-X replaces the Pi3a Attack node with an NVIDIA Jetson Nano, transforming ULTRON from a Raspberry Pi cluster into a **GPU-accelerated AI security platform**. The Jetson Nano's 128-core Maxwell GPU (472 GFLOPS) unlocks capabilities impossible on ARM CPU alone: deep learning intrusion detection, GPU-accelerated password cracking, real-time computer vision for physical security, and reinforcement learning-enhanced honeypots.

The node roles are **rewired** — the Jetson becomes the AI brain, Pi4 handles essential services (MQTT, SMTP, self-healing), and Pi3b becomes a dedicated honeypot platform. This variant targets researchers, red teams, and organizations that need AI-powered threat analysis alongside traditional detection.

**Key Performance Gains:**

| Capability | ULTRON (Pi3a) | ULTRON-X (Jetson Nano) | Improvement |
|------------|---------------|------------------------|-------------|
| IDS throughput | ~1 Gbps (CPU Suricata) | ~1.5 Gbps (GPU Snort/CLort) | 52% faster |
| Password cracking | ~10 KH/s (hashcat CPU) | ~5.4 MH/s (hashcat CUDA) | 540× faster |
| Anomaly detection | Rule-based only | ML models (CNN-GRU, 89%+ accuracy) | New capability |
| Physical security | GPIO tripwire only | Computer vision (YOLOX, 4 FPS) | New capability |
| Honeypot adaptation | Static Cowrie | Adaptive Q-Cowrie (RL-based) | New capability |
| Deep learning inference | Not possible | TFLite/CUDA on 128-core GPU | New capability |

**Cost Impact:** +$99–$149 (Jetson Nano) replaces -$35 (Pi3a removed). Net additional cost: $64–$114. Total ULTRON-X cost: ~$354–$404.

### 26.2 Hardware Comparison

| Component | ULTRON (Pi3a) | ULTRON-X (Jetson Nano) |
|-----------|---------------|------------------------|
| **Board** | Raspberry Pi 3 Model B+ | NVIDIA Jetson Nano (4GB) |
| **Processor** | BCM2837B0, quad-core Cortex-A53 @ 1.4 GHz | Quad-core Cortex-A57 @ 1.43 GHz + 128-core Maxwell GPU |
| **RAM** | 1 GB LPDDR2 | 4 GB LPDDR4 (shared with GPU) |
| **GPU** | VideoCore IV (OpenGL ES 3.0) | 128-core Maxwell (472 GFLOPS, CUDA support) |
| **Storage** | microSD (32 GB) | microSD (64 GB) + optional NVMe via USB 3.0 |
| **Networking** | 100 Mbps Ethernet + 802.11ac WiFi | Gigabit Ethernet + 802.11ac WiFi |
| **USB** | 4× USB 2.0 | 4× USB 3.0, 1× USB 2.0 (micro) |
| **GPIO** | 40-pin header | 40-pin header (Jetson-compatible) |
| **Power** | 5V/2.5A (12.5W max) | 5V/2A (10W) or 5V/4A (20W with GPU boost) |
| **TDP** | ~5W typical | 5–10W (configurable) |
| **Price** | ~$35 | ~$99–$149 |
| **SDK/CUDA** | Not available | JetPack SDK (CUDA, cuDNN, TensorRT, VisionWorks) |
| **AI Frameworks** | Limited (TFLite CPU only) | Full CUDA stack: PyTorch, TensorFlow, TensorRT, ONNX |

### 26.3 Architecture — Rewired Node Roles

```
                    ┌─────────────────────────────────────────────────────┐
                    │              ULTRON-X — Rewired Architecture        │
                    └─────────────────────────────────────────────────────┘

  ┌──────────────────────────── PRODUCTION LAN (192.168.100.0/24) ──────────────────────────┐
  │                                                                                          │
  │  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐  │
  │  │  Production      │   │  Production      │   │  Production      │   │  Production      │  │
  │  │  Server #1       │   │  Server #2       │   │  Server #3       │   │  Server #N       │  │
  │  │  192.168.100.10  │   │  192.168.100.11  │   │  192.168.100.12  │   │  192.168.100.x   │  │
  │  └─────────────────┘   └─────────────────┘   └─────────────────┘   └─────────────────┘  │
  │                                    │                                                       │
  └────────────────────────────────────┼───────────────────────────────────────────────────────┘
                                       │ eth0
                    ┌──────────────────┴──────────────────┐
                    │                                     │
          ┌────────┴────────┐              ┌──────────────┴──────────────┐
          │   Pi3b (.3)     │              │   Jetson Nano (.4)          │
          │   Honeypot Only │              │   AI BRAIN — Core Engine    │
          │                 │              │                             │
          │  eth0: .3       │              │  eth0: .4                   │
          │                 │              │                             │
          │  ┌────────────┐ │              │  ┌────────────────────────┐ │
          │  │ Cowrie     │ │              │  │ GPU-Accelerated IDS    │ │
          │  │ (SSH/Telnet│ │              │  │ (CLort/Suricata+CUDA)  │ │
          │  │  honeypot) │ │              │  │ ~1.5 Gbps throughput   │ │
          │  └────────────┘ │              │  └────────────────────────┘ │
          │  ┌────────────┐ │              │  ┌────────────────────────┐ │
          │  │ Q-Cowrie   │ │              │  │ Deep Learning IDS      │ │
          │  │ (RL-based  │ │              │  │ (CNN-GRU, 89%+ acc.)   │ │
          │  │  adaptive) │ │              │  │ TFLite/CUDA inference  │ │
          │  └────────────┘ │              │  └────────────────────────┘ │
          │  ┌────────────┐ │              │  ┌────────────────────────┐ │
          │  │ Canary     │ │              │  │ GPU Hashcat Engine     │ │
          │  │ Services   │ │              │  │ 5.4 MH/s MD5           │ │
          │  │            │ │              │  │ AI wordlist generation │ │
          │  └────────────┘ │              │  └────────────────────────┘ │
          │  AC600 WiFi (.50)│              │  ┌────────────────────────┐ │
          │  [Management]   │              │  │ Computer Vision (CV)   │ │
          └─────────────────┘              │  │ YOLOX-S body detection │ │
                                           │  │ 4 FPS on Jetson GPU    │ │
                    ┌──────────────────┐   │  └────────────────────────┘ │
                    │  Pi4 (.1)        │   │  ┌────────────────────────┐ │
                    │  SERVICES NODE   │   │  │ Anomaly Detection      │ │
                    │                  │   │  │ Isolation Forest +     │ │
                    │  eth0: .1        │   │  │ Autoencoder (TFLite)   │ │
                    │                  │   │  └────────────────────────┘ │
                    │  ┌────────────┐  │   └─────────────────────────────┘
                    │  │ Mosquitto  │  │              │
                    │  │ MQTT (1883)│  │              │ MQTT
                    │  └────────────┘  │              │
                    │  ┌────────────┐  │   ┌──────────┴──────────┐
                    │  │ SMTP Relay │  │   │  Mosquitto Broker   │
                    │  │ (port 587) │  │   │  on Pi4 (.1:1883)   │
                    │  └────────────┘  │   └─────────────────────┘
                    │  ┌────────────┐  │
                    │  │ Risk Score │  │
                    │  │ Engine     │  │
                    │  └────────────┘  │
                    │  ┌────────────┐  │
                    │  │ Self-Healer│  │
                    │  └────────────┘  │
                    │  ┌────────────┐  │
                    │  │ nmap Scan  │  │
                    │  │ Engine     │  │
                    │  └────────────┘  │
                    │  500GB SSD       │
                    │  [Storage]       │
                    └──────────────────┘

  ┌──────────────────────── WIFI HOTSPOT (192.168.50.0/24) ──────────────────────┐
  │                                                                               │
  │  ┌─────────────────┐         ┌─────────────────┐                             │
  │  │  Operator        │ ◄───── │  Pi3b AC600     │                             │
  │  │  Laptop          │  WiFi  │  192.168.50.1   │                             │
  │  │  DHCP: .100-200  │        │  [Management AP]│                             │
  │  └────────┬────────┘        └─────────────────┘                             │
  │           │                                                                  │
  │           │  Dashboard (Pi4:8080 via WiFi)                                   │
  │           │  SSH Management (Pi4, Jetson, Pi3b via WiFi)                     │
  │           │  MQTT Subscribe (Pi4:1883 via WiFi)                              │
  └───────────┼──────────────────────────────────────────────────────────────────┘
              │
    ┌─────────┴─────────────────────────────────────────────────────────────────┐
    │                    Operator Access Points                                 │
    │  • Dashboard:  http://192.168.50.1:8080 (via Pi4 WiFi)                   │
    │  • SSH (Brain): ssh sentinel@192.168.50.1                                │
    │  • SSH (AI):    ssh sentinel@192.168.50.4  (Jetson, new)                 │
    │  • SSH (Honeypot): ssh sentinel@192.168.50.3                             │
    │  • MQTT Sub:    mosquitto_sub -h 192.168.50.1 -t 'sentinel/#'            │
    └───────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────── USB 3.0 ───────────────────┐
  │                                                │
  │  ┌──────────────────┐   ┌──────────────────┐  │
  │  │  500GB SSD        │   │  TL-WN722N       │  │
  │  │  (ext4, evidence  │   │  (Monitor Mode)  │  │
  │  │   + logs)         │   │  Connected to    │  │
  │  │  Connected to     │   │  Pi4 for wireless│  │
  │  │  Pi4 via USB 3.0  │   │  monitoring      │  │
  │  └──────────────────┘   └──────────────────┘  │
  └────────────────────────────────────────────────┘
```

**Key principle:** The Jetson Nano is the new AI engine — it runs GPU-accelerated IDS, deep learning models, computer vision, and adaptive honeypot logic. Pi4 becomes a lightweight services node (MQTT, SMTP, risk scoring, self-healing). Pi3b is dedicated to deception (Cowrie + canary services + Q-Cowrie adaptation).

### 26.4 Node Role Mapping

| Role | ULTRON (Original) | ULTRON-X (Jetson) | Change |
|------|-------------------|-------------------|--------|
| **AI/ML Engine** | — | Jetson Nano (.4) | **NEW** — GPU-accelerated inference |
| **Core Brain** | Pi4 (.1) | Pi4 (.1) | Reduced scope — services only |
| **Honeypot** | Pi3b (.3) | Pi3b (.3) | Enhanced with Q-Cowrie adaptation |
| **Attack/Scanner** | Pi3a (.2) | Pi4 (.1) | Merged into services node |
| **IDS** | Pi3b (.3) | Jetson Nano (.4) | Moved to GPU (52% faster) |
| **Dashboard** | Pi4 (:8080) | Pi4 (:8080) | Unchanged |
| **MQTT Broker** | Pi4 (:1883) | Pi4 (:1883) | Unchanged |
| **SMTP Relay** | Pi4 (:587) | Pi4 (:587) | Unchanged |
| **Risk Engine** | Pi4 (Python) | Pi4 (Python) | Unchanged |
| **Self-Healer** | Pi4 (Python) | Pi4 (Python) | Unchanged |
| **nmap Scanner** | Pi4 (timer) | Pi4 (timer) | Unchanged |
| **Wireless Monitor** | Pi4 (TL-WN722N) | Pi4 (TL-WN722N) | Unchanged |
| **WiFi AP** | Pi3b (AC600) | Pi3b (AC600) | Unchanged |
| **Storage** | Pi4 (500GB SSD) | Pi4 (500GB SSD) | Unchanged |
| **Physical LEDs** | ESP32-C3 (Pi4 USB) | ESP32-C3 (Pi4 USB) | Unchanged |
| **Physical OLED** | ESP32-C3 (Pi4 USB) | ESP32-C3 (Pi4 USB) | Unchanged |
| **Tripwire** | Pi4 (GPIO) | Pi4 (GPIO) | Unchanged |

### 26.5 GPU Capabilities Deep Dive

#### 26.5.1 GPU-Accelerated Intrusion Detection

The Jetson Nano's 128-core Maxwell GPU enables hardware-accelerated packet inspection that ARM CPUs cannot match.

**CLort Framework:** Academic research demonstrates 52% throughput improvement when running Snort IDS rules on GPU vs CPU. The GPU parallelizes pattern matching across hundreds of rules simultaneously, achieving ~1.5 Gbps sustained throughput on Jetson Nano — critical for production networks where traffic spikes can overwhelm CPU-only IDS.

| IDS Configuration | Throughput | Latency | Detection Rate |
|-------------------|------------|---------|----------------|
| Suricata CPU (Pi3a) | ~1 Gbps | ~2ms | 95% (signature) |
| CLort GPU (Jetson) | ~1.5 Gbps | ~1ms | 95% (signature) + parallel rule eval |
| NanoNIDS (Jetson Orin) | ~2 Gbps | <1ms | 97% (signature + anomaly) |

**NanoNIDS Architecture:** Combines Suricata for signature-based detection with Isolation Forest anomaly detection running as a TFLite model on the GPU. This hybrid approach catches both known threats (signatures) and zero-day attacks (anomaly detection) — a capability only possible with GPU acceleration.

#### 26.5.2 Deep Learning Intrusion Detection

Research on Jetson Nano has validated multiple deep learning architectures for network intrusion detection:

| Model | Dataset | Accuracy | Inference Time | Jetson Nano FPS |
|-------|---------|----------|----------------|-----------------|
| CNN-GRU (ensemble) | UNSW-NB15 | 89.46% | ~15ms/packet | 66 packets/sec |
| CNN+RNN+DNN+LSTM (stacking) | CICIDS2017 | 97.2% | ~20ms/packet | 50 packets/sec |
| Transformer-based | ToN_IoT | 98.1% | ~25ms/packet | 40 packets/sec |
| Autoencoder (TFLite) | SWaT | 96.8% | ~8ms/sample | 125 samples/sec |

**Deployment Strategy:** ULTRON-X runs a lightweight CNN-GRU model via TFLite for real-time inference, with periodic retraining on the Pi4's SSD-stored datasets. The model classifies traffic into: normal, reconnaissance, DoS, exploitation, and C2 communication categories.

**TuringAnomalyDetection Pattern:** Uses a Denoising Autoencoder (DAE) and Sparse Autoencoder trained on normal traffic patterns. Anomalies produce high reconstruction error, triggering alerts. This unsupervised approach requires no labeled attack data — it learns "normal" and flags deviations.

#### 26.5.3 GPU-Accelerated Password Cracking

The Jetson Nano transforms ULTRON from a passive observer into an active offensive capability for authorized penetration testing:

| Hash Type | CPU (Pi3a hashcat) | GPU (Jetson hashcat) | Speedup |
|-----------|--------------------|-----------------------|---------|
| MD5 | ~10 KH/s | ~5.4 MH/s | 540× |
| SHA-1 | ~8 KH/s | ~1.8 MH/s | 225× |
| SHA-256 | ~5 KH/s | ~750 KH/s | 150× |
| NTLM | ~15 KH/s | ~2.5 MH/s | 167× |
| WPA-PMKID | ~5 KH/s | ~120 KH/s | 24× |

**Mr. CrackBot AI Integration:** Based on the Jetson-based project that combines GPU hashcat with AI-powered wordlist generation. The neural network analyzes compromised password patterns to generate targeted wordlists, improving crack rates by 30–40% over dictionary attacks. ULTRON-X can deploy this for authorized credential audits of production servers.

**Compiling hashcat for Jetson Nano:**
```bash
# Flash Jetson Nano with JetPack 4.6.1
git clone https://github.com/hashcat/hashcat.git
cd hashcat && make -j4 CUDA(tensor)=1
# Benchmark
./hashcat -b -m 0  # MD5 benchmark
```

#### 26.5.4 Computer Vision for Physical Security

The Jetson Nano's GPU enables real-time computer vision that extends ULTRON's physical security beyond simple GPIO tripwires:

| Model | Detection | FPS on Jetson | Use Case |
|-------|-----------|---------------|----------|
| YOLOX-S | Body/head/hand | 4 FPS | Intruder detection in server room |
| MobileNet-SSD | Person/face | 8 FPS | Access control verification |
| OpenPose | Pose estimation | 2 FPS | Behavioral analysis (aggressive posture) |

**Integration with ULTRON:** The CV pipeline publishes detections to MQTT (`sentinel/cv/intruder`), feeding into the risk scoring engine. A person detected in the server room after hours adds +15 to the risk score. Multiple rapid movements (possible theft) add +25.

**Power Consideration:** Running YOLOX-S at 4 FPS consumes ~5W GPU power, bringing total Jetson consumption to ~10W — still within the 5V/2A power supply limit. For sustained CV workloads, the 5V/4A supply is recommended.

#### 26.5.5 Adaptive Honeypot (Q-Cowrie)

The Jetson Nano runs a reinforcement learning agent that enhances Cowrie's deception capabilities:

**Markov Decision Process (MDP):**
- **State:** Attacker behavior profile (skill level, tools used, time spent, commands executed)
- **Actions:** Simulate different OS fingerprints, adjust response delays, present varied file systems
- **Reward:** Engagement duration × data quality (unique commands logged, tools identified)

**MITRE ATT&CK Alignment:** Q-Cowrie maps attacker techniques to MITRE ATT&CK framework in real-time, enabling ULTRON to classify adversary TTPs during the engagement — not just after.

**Performance:** The RL inference runs at <10ms per decision on the Jetson GPU, enabling real-time adaptation without perceptible delay to the attacker.

### 26.6 MQTT Topic Extensions

ULTRON-X adds new MQTT topics for GPU-accelerated services:

```json
// GPU IDS Alerts (Jetson → Pi4 Risk Engine)
{
  "topic": "sentinel/ids/gpu/alert",
  "payload": {
    "timestamp": "2026-09-15T10:30:00Z",
    "source": "clort-gpu",
    "signature_id": 2013028,
    "signature": "ET POLICY Outbound Connection to IPMI",
    "src_ip": "192.168.100.15",
    "dst_ip": "192.168.100.10",
    "src_port": 4444,
    "dst_port": 623,
    "proto": "udp",
    "severity": 3,
    "confidence": 0.94,
    "gpu_inference_ms": 1.2
  }
}

// Deep Learning Anomaly Detection (Jetson → Pi4 Risk Engine)
{
  "topic": "sentinel/ids/ml/anomaly",
  "payload": {
    "timestamp": "2026-09-15T10:30:05Z",
    "model": "cnn-gru-v2",
    "classification": "reconnaissance",
    "confidence": 0.89,
    "features_extracted": 42,
    "inference_ms": 14.7,
    "src_ip": "192.168.100.20",
    "risk_contribution": 12
  }
}

// Computer Vision Detection (Jetson → Pi4 Risk Engine)
{
  "topic": "sentinel/cv/intruder",
  "payload": {
    "timestamp": "2026-09-15T22:15:00Z",
    "model": "yolox-s",
    "detection": "person",
    "confidence": 0.92,
    "location": "server-room-cam-1",
    "bounding_box": [120, 80, 340, 480],
    "fps": 4.1,
    "risk_contribution": 15
  }
}

// GPU Hashcat Status (Jetson → Dashboard)
{
  "topic": "sentinel/attack/hashcat/status",
  "payload": {
    "status": "running",
    "hash_type": "WPA-PMKID",
    "speed": "120.5 KH/s",
    "progress": "23.4%",
    "eta": "2h 15m",
    "gpu_temp": "67°C",
    "gpu_utilization": 89
  }
}

// Q-Cowrie Adaptive Honeypot (Pi3b ↔ Jetson)
{
  "topic": "sentinel/honeypot/qcowrie/state",
  "payload": {
    "attacker_ip": "192.168.100.25",
    "skill_estimate": "intermediate",
    "mitre_techniques": ["T1059.004", "T1021.004"],
    "current_action": "simulate-linux-kernel-4.15",
    "engagement_score": 7.2,
    "data_collected": ["credentials", "tools", "lateral_movement"]
  }
}
```

### 26.7 Systemd Services (Jetson-Specific)

```ini
# /etc/systemd/system/sentinel-gpu-ids.service
[Unit]
Description=ULTRON GPU-Accelerated IDS (CLort/CUDA)
After=network-online.target mosquitto.service
Wants=network-online.target

[Service]
Type=simple
User=sentinel
ExecStart=/opt/sentinel/bin/gpu_ids --config /etc/sentinel/gpu-ids.conf
Restart=always
RestartSec=5
Environment=CUDA_VISIBLE_DEVICES=0

[Install]
WantedBy=multi-user.target

# /etc/systemd/system/sentinel-ml-engine.service
[Unit]
Description=ULTRON Deep Learning IDS Engine
After=network-online.target sentinel-gpu-ids.service
Wants=network-online.target

[Service]
Type=simple
User=sentinel
ExecStart=/opt/sentinel/bin/ml_engine --model /opt/sentinel/models/cnn-gru-v2.tflite
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# /etc/systemd/system/sentinel-cv-engine.service
[Unit]
Description=ULTRON Computer Vision Security Engine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sentinel
ExecStart=/opt/sentinel/bin/cv_engine --model /opt/sentinel/models/yolox-s.onnx
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 26.8 Cost Analysis

| Component | ULTRON (Original) | ULTRON-X (Jetson) | Delta |
|-----------|-------------------|-------------------|-------|
| Pi4 8GB | $75 | $75 | $0 |
| Pi3b (IDS) | $35 | — | -$35 |
| Pi3b (Attack) | $35 | — | -$35 |
| Jetson Nano (4GB) | — | $99–$149 | +$99–$149 |
| 500GB SSD | $45 | $45 | $0 |
| TL-WN722N | $15 | $15 | $0 |
| AC600 WiFi | $20 | $20 | $0 |
| 128GB Pendrive | $15 | $15 | $0 |
| 5-port Switch | $15 | $15 | $0 |
| ESP32-C3 (×2) | $10 | $10 | $0 |
| MicroSD cards | $20 | $25 (64GB for Jetson) | +$5 |
| Power supplies | $15 | $15 | $0 |
| **Total** | **$290** | **$354–$404** | **+$64–$114** |

**Cost per capability added:**
- GPU IDS acceleration (52% faster): ~$15 (amortized)
- Deep learning anomaly detection: ~$25
- Computer vision physical security: ~$25
- GPU password cracking (540× faster): ~$15
- Adaptive honeypot (Q-Cowrie): ~$15

**ROI:** For organizations where a single prevented breach justifies the $64–$114 premium, ULTRON-X delivers enterprise-grade AI security at 5% of the cost of commercial alternatives ($5K–$20K for managed SIEM + SOAR platforms).

### 26.9 Deployment Considerations

#### Power Budget

| Component | ULTRON (Pi-only) | ULTRON-X (with Jetson) |
|-----------|-------------------|------------------------|
| Pi4 (services) | 5W | 5W |
| Pi3b (honeypot) | 3W | 3W |
| Jetson Nano (idle) | — | 5W |
| Jetson Nano (GPU load) | — | 10W |
| SSD + peripherals | 3W | 3W |
| **Total** | **11W** | **16–21W** |

Jetson Nano requires a quality 5V/4A (20W) power supply for sustained GPU workloads. The official NVIDIA barrel-jack supply is recommended; USB-C supplies may cause voltage drops under load.

#### Thermal Management

The Jetson Nano throttles at 80°C. Under sustained GPU load (IDS + CV + hashcat), temperatures reach 65–75°C. Recommendations:
- Active cooling fan (5V, connects to Jetson 40-pin header): keeps temps below 60°C
- Heat sink + thermal paste on the SoC: reduces temps by 10–15°C
- Open-air case (not enclosed): allows natural convection

#### Storage

Jetson Nano's eMMC is limited (16GB on 4GB model). Use microSD for OS + models, and mount the Pi4's 500GB SSD via NFS for:
- Training datasets (UNSW-NB15, CICIDS2017, ToN_IoT)
- Model checkpoints
- Long-term evidence storage
- GPU IDS logs (higher volume than CPU IDS)

#### Network Bandwidth

With 1 Gbps Ethernet on the Jetson (vs 100 Mbps on Pi3), the ULTRON-X variant can monitor higher-bandwidth networks. For networks exceeding 1 Gbps, consider:
- Jetson AGX Orin (2048 CUDA cores, 275 TOPS, ~$599)
- Multiple Jetson Nanos with load balancing
- SmartNIC offload (PAMO architecture: 80 Gbps)

### 26.10 When to Choose ULTRON-X

| Choose ULTRON (Original) | Choose ULTRON-X (Jetson) |
|--------------------------|--------------------------|
| Budget-constrained (<$300) | Research / red team / advanced lab |
| Networks < 100 Mbps | Networks > 100 Mbps |
| No need for ML-based detection | Need deep learning anomaly detection |
| Physical security = GPIO tripwire only | Need computer vision (server room monitoring) |
| Honeypot = static Cowrie | Need adaptive, RL-enhanced honeypot |
| Credential auditing not required | Need GPU hashcat for authorized pentesting |
| Minimal power budget (<15W) | Power budget allows 15–25W |
| Simple deployment (3 boards) | Can manage 2 boards (Jetson replaces 2 Pis) |

**Hybrid Approach:** Deploy ULTRON-X alongside the original ULTRON for organizations that need both affordable baseline protection (Pi cluster) and AI-powered deep analysis (Jetson). The Jetson publishes to the same MQTT bus, enabling a unified dashboard across both systems.

---

## 27. Troubleshooting

### 27.1 Common Issues

| Symptom | Likely Cause | Resolution |
|---------|-------------|------------|
| LED stays off | ESP32-C3 not receiving serial commands | Check USB connection, verify serial port, restart ESP32 |
| Risk score stuck at 0 | Risk engine not receiving MQTT events | Check MQTT broker is running, verify credentials in risk engine config |
| Dashboard shows "offline" | WebSocket connection failed | Check port 9001 is open, verify MQTT WebSocket config |
| Email not sending | SMTP credentials wrong or port blocked | Test with `mosquitto_pub`, verify SMTP config in `/etc/sentinel/smtp.conf` |
| Cowrie not logging | Cowrie service not running | `sudo systemctl status cowrie`, check logs in `/var/log/cowrie/` |
| Scanner not running | Timer not enabled | `sudo systemctl enable --now scanner-nmap.timer` |
| Self-healer not fixing | Circuit breaker open | Check SQLite for breaker state, wait 10 minutes |
| WiFi AP not visible | hostapd or dnsmasq not running | Check both services, verify AC600 is recognized |
| Tripwire not triggering | GPIO wire disconnected | Check physical connection, test with multimeter |
| Disk full | Log rotation not working | `sudo journalctl --vacuum-size=100M`, check logrotate config |

### 27.2 Debug Commands

| Purpose | Command |
|---------|---------|
| Check all services | `systemctl status sentinel-* mosquitto cowrie suricata` |
| View MQTT traffic | `mosquitto_sub -h localhost -t 'sentinel/#' -v` |
| Test MQTT publish | `mosquitto_pub -h localhost -t 'sentinel/risk/current' -m '{"score":50}'` |
| Check risk score | `mosquitto_sub -h localhost -t 'sentinel/risk/current' -C 1` |
| View Cowrie logs | `tail -f /var/log/cowrie/cowrie.json` |
| Check Suricata alerts | `tail -f /var/log/suricata/fast.log` |
| Test email | `python3 -c "import smtplib; ..."` (see alert config) |
| Check disk usage | `df -h /var/lib/sentinel /media/pendrive` |
| Check CPU temperature | `vcgencmd measure_temp` |
| Test tripwire | `echo 0 > /sys/class/gpio/gpio17/value` (simulate trigger) |

---

## 28. Glossary & References

### 28.1 Glossary

| Term | Definition |
|------|-----------|
| **ULTRON** | Unified Layer for Threat Response, Observability & Network defense — the system name |
| **Risk Score** | A 0–100 integer representing the current threat level, computed from six weighted components |
| **Risk Band** | A color category (GREEN/YELLOW/RED/PURPLE) derived from the risk score range |
| **Canary** | A decoy file or service that triggers alerts when accessed by unauthorized users |
| **Cowrie** | Open-source SSH/Telnet honeypot that logs attacker interactions |
| **Suricata** | Open-source network IDS/IPS engine using signature-based detection |
| **Self-Healing** | Automated remediation of security misconfigurations using predefined templates |
| **Tripwire** | A physical sensor (GPIO wire) that detects enclosure tampering |
| **MQTT** | Message Queuing Telemetry Transport — lightweight pub/sub messaging protocol |
| **Mosquitto** | Open-source MQTT broker |
| **nmap** | Network exploration and security auditing tool |
| **Nuclei** | Template-based vulnerability scanner |
| **Lynis** | Unix system auditing and hardening tool |
| **Nftables** | Linux kernel packet filtering framework (successor to iptables) |
| **Circuit Breaker** | A pattern that pauses remediation after repeated failures to prevent infinite loops |
| **ZTNA** | Zero Trust Network Access — encrypted mesh networking (future enhancement) |
| **CTF** | Capture The Flag — cybersecurity competition format |
| **ULTRON-X** | Jetson Nano variant of ULTRON with GPU-accelerated AI capabilities |
| **Jetson Nano** | NVIDIA edge AI platform — 128-core Maxwell GPU, 4GB RAM, CUDA support |
| **CUDA** | NVIDIA's parallel computing platform for GPU-accelerated computation |
| **GPU** | Graphics Processing Unit — massively parallel processor for AI/ML workloads |
| **CLort** | GPU-accelerated Snort IDS framework achieving 52% faster throughput |
| **NanoNIDS** | Network IDS combining Suricata + Isolation Forest anomaly detection on Jetson |
| **Q-Cowrie** | Reinforcement learning-enhanced Cowrie honeypot with adaptive attacker engagement |
| **YOLOX** | Single-stage object detector optimized for edge deployment (Jetson) |
| **hashcat** | Password recovery tool with GPU acceleration (CUDA/OpenCL) |
| **TFLite** | TensorFlow Lite — lightweight ML inference framework for edge devices |
| **TensorRT** | NVIDIA's deep learning inference optimizer and runtime for Jetson |
| **CNN-GRU** | Convolutional + Gated Recurrent Unit neural network for traffic classification |
| **Isolation Forest** | Unsupervised anomaly detection algorithm for network traffic |
| **Autoencoder** | Neural network that learns normal patterns; anomalies produce high reconstruction error |
| **MDP** | Markov Decision Process — mathematical framework for reinforcement learning |
| **MITRE ATT&CK** | Adversarial tactics, techniques, and knowledge base for threat classification |

### 28.2 References

**Core ULTRON Components:**

1. Mosquitto MQTT Broker — https://mosquitto.org
2. Cowrie Honeypot — https://github.com/cowrie/cowrie
3. Suricata IDS/IPS — https://suricata.io
4. nmap Security Scanner — https://nmap.org
5. Nuclei Vulnerability Scanner — https://github.com/projectdiscovery/nuclei
6. Lynis System Auditor — https://cisofy.com/lynis/
7. nftables — https://www.netfilter.org/projects/nftables/
8. ESP32 Arduino Core — https://github.com/espressif/arduino-esp32
9. WS2812B NeoPixel Library — https://github.com/adafruit/Adafruit_NeoPixel
10. Raspberry Pi Documentation — https://www.raspberrypi.com/documentation/
11. MQTT v3.1.1 Specification — https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html
12. MIT License — https://opensource.org/licenses/MIT

**GPU-Accelerated Intrusion Detection (§26.5.1):**

13. CLort: GPU-Accelerated Snort — Achieves 52% faster IDS throughput on NVIDIA GPUs via CUDA parallelized pattern matching. Demonstrated on Jetson-class hardware.
14. PAMO: SmartNIC-Accelerated Network Monitoring — 80 Gbps intrusion detection using FPGA SmartNIC offload with CPU fallback for complex analysis. USENIX ATC 2023.
15. NVIDIA Morpheus AI Framework — GPU-accelerated cybersecurity pipeline for real-time threat detection. Sustains ~19Gbps zero-day detection using Triton Inference Server.
16. NanoNIDS: Network Intrusion Detection on Jetson — Suricata + Isolation Forest anomaly detection running on Jetson Orin Nano. Combines signature-based and ML-based detection.

**Deep Learning IDS (§26.5.2):**

17. CNN-GRU Ensemble for IoT Intrusion Detection — 89.46% accuracy on UNSW-NB15 dataset, validated on Jetson Nano GPU. Combines convolutional feature extraction with gated recurrent temporal analysis.
18. Stacking Ensemble (CNN+RNN+DNN+LSTM) — 97-99% accuracy on CICIDS2017, ToN_IoT, and SWaT datasets. Multi-architecture ensemble with majority voting.
19. TuringAnomalyDetection — Distributed IoT security gateway using Jetson Nano for TFLite ML inference. Denoising Autoencoder + Sparse Autoencoder for unsupervised anomaly detection.
20. Transformer-Based Network Anomaly Detection — Self-attention mechanism achieving 98.1% accuracy on ToN_IoT dataset. Higher inference latency but superior pattern recognition.

**GPU-Accelerated Password Cracking (§26.5.3):**

21. hashcat GPU Cracking — Password recovery tool with CUDA/OpenCL acceleration. Jetson Nano achieves 5.4 MH/s MD5, compiled from source with CUDA support.
22. Mr. CrackBot AI — Jetson-based project combining GPU hashcat with AI-powered wordlist generation using neural networks. Analyzes compromised password patterns for targeted attacks.

**Adaptive Honeypot (§26.5.5):**

23. Q-Cowrie: Reinforcement Learning-Enhanced Cowrie — MDP-based adaptive honeypot that adjusts OS fingerprint, response timing, and file system presentation based on attacker behavior. MITRE ATT&CK technique mapping during engagement.

**Computer Vision Security (§26.5.4):**

24. YOLOX-S on Jetson — Body/head/hand detection at 4 FPS on Jetson Nano GPU. Single-stage detector optimized for edge deployment with TensorRT.
25. MaVIS: Machine Vision for Industrial Security — Camera-based perimeter monitoring with real-time person detection and alerting.
26. jetson-security-cam — Open-source Jetson-based security camera with person detection, face recognition, and MQTT alerting.

**Jetson Platform:**

27. NVIDIA Jetson Nano Developer Kit — 128-core Maxwell GPU, 4GB LPDDR4, quad-core Cortex-A57, JetPack SDK (CUDA, cuDNN, TensorRT, VisionWorks).
28. NVIDIA JetPack SDK — Development toolkit for Jetson platforms including CUDA, cuDNN, TensorRT, and VisionWorks libraries.
29. NVIDIA DeepStream SDK — AI-based video analytics pipeline for Jetson platforms. Enables multi-camera real-time inference.

---

> **Document Version:** 6.8
> **Last Updated:** September 2026
> **License:** MIT
> **Contact:** [Your Email]
> **Repository:** https://github.com/[your-username]/ultron
