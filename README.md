<div align="center">

# 🛡️ ULTRON

## Unified Layer for Threat Response, Observability & Network Defense

**An autonomous cybersecurity appliance built on Raspberry Pi — $290 total cost**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Black Hat Asia 2027](https://img.shields.io/badge/Black%20Hat%20Asia-2027-red.svg)](https://www.blackhat.com/asia-27/arsenal.html)
[![Hardware](https://img.shields.io/badge/Hardware-Raspberry%20Pi-green.svg)](https://www.raspberrypi.com/)
[![Cost](https://img.shields.io/badge/Cost-%24290-blue.svg)](#-bill-of-materials)
[![Zero Cloud](https://img.shields.io/badge/Cloud-Zero%20dependency-orange.svg)](#-design-philosophy)

</div>

---

## 📋 Table of Contents

1. [Abstract](#-abstract)
2. [Key Features](#-key-features)
3. [Architecture Overview](#-architecture-overview)
4. [Hardware Design](#-hardware-design)
5. [System Architecture](#-system-architecture)
6. [Risk Scoring Engine](#-risk-scoring-engine)
7. [Operating Modes](#-operating-modes)
8. [Installation](#-installation)
9. [Usage](#-usage)
10. [Dashboard](#-dashboard)
11. [Troubleshooting](#-troubleshooting)
12. [Contributing](#-contributing)
13. [License](#-license)

---

## 🎯 Abstract

ULTRON is a self-contained, autonomous cybersecurity appliance built entirely on Raspberry Pi hardware. It is a **modular device** — connect it to any server room via Ethernet and it immediately begins monitoring, detecting, scanning, and protecting.

The core innovation is a **risk-scoring engine** that fuses signals from multiple detection layers — network scanning, honeypot canary events, intrusion detection, wireless monitoring, and physical tripwire sensors — into a single 0–100 risk score. This score drives automated response: from passive monitoring at green, through active defense at yellow, to full quarantine at red.

**Key Statistics:**
- 💰 **Total Cost:** ~$290 (3 Raspberry Pi nodes + peripherals)
- 🔧 **Minimum Admin:** 1 person (or fully autonomous)
- 🌐 **Zero Cloud:** All processing local, no external dependencies
- 🎓 **Dual Mode:** Production security + CTF training platform

---

## ✨ Key Features

<table>
<tr>
<td width="50%">

### 🔍 **Autonomous Monitoring**
- Network intrusion detection (Suricata IDS/IPS)
- SSH honeypot (Cowrie) with canary files
- Vulnerability scanning (nmap + Nuclei + Lynis)
- Real-time traffic analysis on wired LAN

</td>
<td width="50%">

### 🧠 **Intelligent Response**
- Risk scoring engine (0-100 scale)
- Automated self-healing framework
- Circuit breaker pattern for safety
- Email alerts for critical events

</td>
</tr>
<tr>
<td width="50%">

### 🔌 **Physical Security**
- NeoPixel LED threat visualization
- OLED status display
- Tripwire sensors with buzzer alarm
- Enclosure tamper detection

</td>
<td width="50%">

### 🎓 **Educational Platform**
- CTF training mode (LAB mode)
- Real-time leaderboard
- Hands-on security challenges
- Learn offensive & defensive skills

</td>
</tr>
</table>

---

## 🏗️ Architecture Overview

### System Architecture Diagram

<div align="center">

```mermaid
graph TB
    subgraph "Production LAN (192.168.100.0/24)"
        S1[Server 1<br/>192.168.100.10]
        S2[Server 2<br/>192.168.100.20]
        S3[Server N<br/>192.168.100.x]
    end

    subgraph "ULTRON System"
        subgraph "Pi4 - Brain (192.168.100.1)"
            MQTT[Mosquitto<br/>MQTT Broker]
            RISK[Risk Engine]
            SCAN[Scanner Engine]
            SELF[Self-Healer]
            ALERT[Alert System]
            DASH[Dashboard<br/>Port 8080]
        end

        subgraph "Pi3a - Attack (192.168.100.2)"
            COWRIE[Cowrie<br/>SSH Honeypot]
            CANARY[Canary Bridge]
            LURE[Web Lure]
        end

        subgraph "Pi3b - IDS (192.168.100.3)"
            SURICATA[Suricata<br/>IDS/IPS]
            AGGREGATOR[Dashboard<br/>Aggregator]
            WIFI[AC600<br/>WiFi AP]
        end

        subgraph "ESP32 Layer"
            ESP32C3[ESP32-C3<br/>NeoPixel + OLED]
            ESP32WR[ESP32-WROOM<br/>Tripwire]
        end
    end

    subgraph "Management Network (192.168.50.0/24)"
        LAPTOP[Operator<br/>Laptop]
    end

    S1 & S2 & S3 -->|Ethernet| SWITCH[5-Port Switch]
    SWITCH -->|Ethernet| Pi4 & Pi3a & Pi3b
    
    Pi4 --> MQTT
    MQTT --> RISK & SCAN & SELF & ALERT & DASH
    
    Pi3a --> COWRIE & CANARY & LURE
    COWRIE & CANARY & LURE -->|MQTT| MQTT
    
    Pi3b --> SURICATA & AGGREGATOR & WIFI
    SURICATA -->|MQTT| MQTT
    
    WIFI -.->|WiFi| LAPTOP
    LAPTOP -->|HTTP| DASH
    
    ESP32C3 -->|Serial| Pi4
    ESP32WR -->|GPIO| Pi3a & Pi3b
```

</div>

### Data Flow Pipeline

<div align="center">

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ DETECT  │───▶│ COLLECT │───▶│  SCORE  │───▶│ DECIDE  │───▶│ RESPOND │───▶│ REPORT  │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
     │              │              │              │              │              │
     │              │              │              │              │              │
 Sensors       MQTT Events    Risk Score     Risk Band     Firewall      Dashboard
 detect        publish to     clamp(0..100,  threshold     rules,        + Email
 anomalies     broker         Σ × weights)   check         restart       + .md report
```

</div>

---

## 🔧 Hardware Design

### Bill of Materials

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

### Physical Layout

<div align="center">

```
┌─────────────────────────────────────────────────────────────┐
│                    ULTRON PHYSICAL LAYOUT                    │
│                                                             │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐                    │
│   │  Pi4    │  │  Pi3a   │  │  Pi3b   │                    │
│   │  Brain  │  │  Attack │  │  IDS    │                    │
│   │ 8GB RAM │  │ 1GB     │  │ 1GB     │                    │
│   └────┬────┘  └────┬────┘  └────┬────┘                    │
│        │            │            │                          │
│   ┌────┴────┐  ┌────┴────┐  ┌────┴────┐                    │
│   │USB Hub  │  │TL-WN722N│  │AC600    │                    │
│   │SSD+ESP32│  │Monitor  │  │Hotspot  │                    │
│   └─────────┘  └─────────┘  └─────────┘                    │
│        │            │            │                          │
│   ┌────┴────────────┴────────────┴────┐                     │
│   │        5-Port Ethernet Switch      │                     │
│   └───────────────────────────────────┘                     │
│                                                             │
│   ┌─────────┐  ┌─────────┐                                 │
│   │ESP32-C3 │  │ESP32-WR │                                 │
│   │NeoPixel │  │Tripwire │                                 │
│   │OLED     │  │Portal   │                                 │
│   └─────────┘  └─────────┘                                 │
│                                                             │
│   ┌─────────┐                                              │
│   │500GB SSD│  ← USB 3.0 to Pi4                            │
│   │NAS/Vault│                                              │
│   └─────────┘                                              │
└─────────────────────────────────────────────────────────────┘
```

</div>

### Power Distribution

<div align="center">

```
AC Outlet (230V)
├── DC 5V 3A Adapter ──── Pi4 (USB-C)
│                           └── USB Hub ── ESP32-C3 (NeoPixel + OLED)
│                                     └── 500GB SSD
├── DC 5V 2.5A Adapter ── Pi3a (Micro-USB) + TL-WN722N
└── DC 5V 2.5A Adapter ── Pi3b (Micro-USB) + AC600

USB Fan ── Pi4 USB port (5V 0.5A)
```

</div>

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

---

## 🏛️ System Architecture

### Node Roles

<table>
<tr>
<td width="33%">

### 🧠 Pi4 — The Brain

**Hardware:** Raspberry Pi 4 Model B, 8GB RAM  
**IP:** 192.168.100.1 (LAN)

**Services:**
- Mosquitto MQTT broker
- Risk scoring engine
- Scanner engine (nmap + Nuclei + Lynis)
- Self-healing framework
- Alert system (SMTP)
- Dashboard (Port 8080)
- Evidence manager

</td>
<td width="33%">

### ⚔️ Pi3a — Attack Node

**Hardware:** Raspberry Pi 3 Model B+, 1GB RAM  
**IP:** 192.168.100.2 (LAN)

**Services:**
- Cowrie SSH honeypot
- Canary bridge (auditd)
- Web lure (fake admin page)
- TL-WN722N (monitor mode)

</td>
<td width="33%">

### 🛡️ Pi3b — IDS Gateway

**Hardware:** Raspberry Pi 3 Model B+, 1GB RAM  
**IP:** 192.168.100.3 (LAN)

**Services:**
- Suricata IDS/IPS
- Dashboard aggregator
- AC600 WiFi hotspot
- dnsmasq (DHCP + DNS)

</td>
</tr>
</table>

### Network Topology

<div align="center">

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
         │ .1      │  │  .2     │    │    .3     │
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

</div>

### MQTT Topic Hierarchy

<div align="center">

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

</div>

---

## 📊 Risk Scoring Engine

### Formula

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

### Component Weights

| Component | Weight (W) | Max Contribution | Signal Source | Decay Rate |
|-----------|-----------|-----------------|---------------|------------|
| Canary events | 0.25 | 25 | Pi3a honeypot + file access | 2 pts/10s |
| Rule alerts | 0.20 | 20 | Suricata IDS signatures | 2 pts/10s |
| Scanner findings | 0.15 | 15 | nmap/Nuclei/Lynis results | 2 pts/10s |
| IDS alerts | 0.15 | 15 | Suricata + wireless anomalies | 2 pts/10s |
| Tripwire | 0.15 | 15 | ESP32-WROOM GPIO sensors | 2 pts/10s |
| Behavioral | 0.10 | 10 | Unusual traffic patterns | 2 pts/10s |

### Risk Bands

<div align="center">

| Band | Range | Color | LED Animation | Response |
|------|-------|-------|---------------|----------|
| 🟢 **GREEN** | 0–29 | Green | Breathing (slow pulse) | Normal monitoring. No action. |
| 🟡 **YELLOW** | 30–59 | Yellow | Chasing (sequential LEDs) | Increase scan frequency. Enable detailed logging. |
| 🔴 **RED** | 60–84 | Red | Strobe (fast flash) | Activate IPS mode. Block IPs. Email alert. |
| 🟣 **PURPLE** | 85–100 | Purple | Pulsing + sparkle | Full quarantine. Tripwire buzzer. All ports blocked. |

</div>

### Decay Logic

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

---

## 🔄 Operating Modes

### ULTRON Mode (Full Protection)

<table>
<tr>
<td width="50%">

**Active Services:**
- ✅ Scanner: Automatic 15-minute cycles
- ✅ Risk Engine: Continuous scoring
- ✅ Self-Healer: Auto-remediation
- ✅ Suricata: IDS → IPS when score > 60
- ✅ Canary Bridge: Active monitoring
- ✅ Alerts: Email notifications
- ✅ Dashboard: Real-time updates
- ✅ ESP32 LED: Live risk band color
- ✅ TL-WN722N: Monitor mode only

</td>
<td width="50%">

**Default Mode**

The system boots into ULTRON mode unless explicitly configured for LAB.

All services operate autonomously 24/7 without human intervention.

Risk scoring drives automated response. ESP32 LED shows real-time threat posture.

</td>
</tr>
</table>

### LAB Mode (CTF Training)

<table>
<tr>
<td width="50%">

**Active Services:**
- ✅ Scanner: Manual only (student-triggered)
- ✅ Risk Engine: Scores, but auto-response disabled
- ✅ Self-Healer: Monitor-only (no auto-fix)
- ✅ Suricata: IDS mode only (never IPS)
- ✅ Canary Bridge: Active (students interact)
- ✅ Alerts: Dashboard only (no email)
- ✅ Dashboard: Leaderboard + manual scan buttons
- ✅ ESP32 LED: Shows risk band, no auto-quarantine
- ✅ TL-WN722N: Full attack capability

</td>
<td width="50%">

**Educational Mode**

Transforms the security appliance into a live CTF training environment.

Students perform scans, crack defenses, and earn leaderboard points against a real, functioning security stack.

Challenges: Port Scan, Vuln Hunt, System Audit, WiFi Recon, Honeypot Escape, Full Compromise, Self-Heal Bypass

</td>
</tr>
</table>

---

## 🚀 Installation

### Prerequisites

- 3× Raspberry Pi (1× Pi4 8GB, 2× Pi3B+)
- 2× ESP32 microcontrollers
- All hardware listed in [Bill of Materials](#-bill-of-materials)
- Ethernet switch connected to server room LAN
- Operator laptop with WiFi capability

### Step 1: Flash OS Images

```bash
# Download Raspberry Pi OS Lite (64-bit)
# Flash to microSD cards using Raspberry Pi Imager
# Enable SSH, set hostname, configure WiFi (for Pi3b only)
```

### Step 2: Configure Network

```bash
# Pi4: Static IP 192.168.100.1
sudo nano /etc/dhcpcd.conf
# interface eth0
# static ip_address=192.168.100.1/24

# Pi3a: Static IP 192.168.100.2
sudo nano /etc/dhcpcd.conf
# interface eth0
# static ip_address=192.168.100.2/24

# Pi3b: Static IP 192.168.100.3
sudo nano /etc/dhcpcd.conf
# interface eth0
# static ip_address=192.168.100.3/24
```

### Step 3: Install Dependencies

```bash
# On all Pi nodes
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip mosquitto mosquitto-clients

# On Pi4 (Brain)
sudo apt install -y sqlite3 nmap nuclei lynis

# On Pi3a (Attack)
sudo apt install -y cowrie auditd

# On Pi3b (IDS)
sudo apt install -y suricata hostapd dnsmasq
```

### Step 4: Configure MQTT Broker

```bash
# On Pi4
sudo nano /etc/mosquitto/mosquitto.conf
# listener 1883
# allow_anonymous false
# password_file /etc/mosquitto/passwd
# acl_file /etc/mosquitto/acl

# Create password file
sudo mosquitto_passwd -c /etc/mosquitto/passwd pi4-core
sudo mosquitto_passwd -b /etc/mosquitto/passwd pi3a-canary <password>
sudo mosquitto_passwd -b /etc/mosquitto/passwd pi3b-ids <password>
# ... add other users

sudo systemctl restart mosquitto
```

### Step 5: Deploy ULTRON Services

```bash
# Clone repository on each node
git clone https://github.com/[your-username]/ultron.git
cd ultron

# Install Python dependencies
pip3 install -r requirements.txt

# Copy service files
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start services
sudo systemctl enable --now sentinel-risk.service
sudo systemctl enable --now sentinel-scanner.timer
# ... enable other services
```

### Step 6: Flash ESP32 Firmware

```bash
# Using Arduino IDE or PlatformIO
# Install ESP32 board support
# Flash NeoPixel + OLED firmware to ESP32-C3
# Flash Tripwire + Portal firmware to ESP32-WROOM
```

---

## 📖 Usage

### Accessing the Dashboard

1. Connect your laptop to `SENTINEL-SECURE` WiFi (created by Pi3b's AC600)
2. Open browser to `http://192.168.100.1:8080`
3. Dashboard shows real-time system status

### Monitoring System Status

```bash
# Check all services
systemctl status sentinel-* mosquitto cowrie suricata

# View MQTT traffic
mosquitto_sub -h localhost -t 'sentinel/#' -v

# Check risk score
mosquitto_sub -h localhost -t 'sentinel/risk/current' -C 1
```

### Switching Modes

```bash
# Switch to LAB mode
mosquitto_pub -h localhost -t 'sentinel/mode' -m '{"mode":"LAB"}'

# Switch to ULTRON mode
mosquitto_pub -h localhost -t 'sentinel/mode' -m '{"mode":"ULTRON"}'
```

### Manual Scan (LAB Mode Only)

```bash
# Trigger nmap scan
mosquitto_pub -h localhost -t 'sentinel/scan/trigger' -m '{"scanner":"nmap","target":"192.168.100.0/24"}'
```

---

## 📊 Dashboard

The dashboard is a **single HTML file** served from Pi4 on port 8080. It uses no frameworks, no build tools — pure HTML + CSS + vanilla JavaScript.

### Panel Layout

<div align="center">

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

</div>

### Real-Time Updates

The dashboard uses WebSocket to receive live MQTT messages. When a new event arrives:

1. Parse the MQTT payload (JSON)
2. Update the relevant panel (risk score, alert list, scan results)
3. If risk band changed, update the color theme of the entire dashboard
4. Animate transitions (smooth color changes, alert slide-in)

---

## 🔧 Troubleshooting

### Common Issues

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

### Debug Commands

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

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Guidelines

- Follow PEP 8 for Python code
- Add tests for new features
- Update documentation as needed
- Use conventional commits format

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Raspberry Pi Foundation](https://www.raspberrypi.com/) for affordable hardware
- [Mosquitto](https://mosquitto.org/) for MQTT broker
- [Cowrie](https://github.com/cowrie/cowrie) for SSH honeypot
- [Suricata](https://suricata.io/) for IDS/IPS
- [nmap](https://nmap.org/) for network scanning
- [Nuclei](https://github.com/projectdiscovery/nuclei) for vulnerability scanning
- [Lynis](https://cisofy.com/lynis/) for system auditing

---

<div align="center">

**Built with ❤️ for the cybersecurity community**

[![Black Hat Asia 2027](https://img.shields.io/badge/Black%20Hat%20Asia-2027-Arsenal-red)](https://www.blackhat.com/asia-27/arsenal.html)

</div>
