# ULTRON — Architecture (In-Depth)

> **Companion docs:** [`README.md`](README.md) (pitch) · [`dashboard.md`](dashboard.md) (UI spec) · [`promt.md`](promt.md) (AI operating brief) · [`blackhat.md`](blackhat.md) (full spec)

---

## 1. System Overview

ULTRON is a **two-plane, five-node IoT cybersecurity ecosystem**:

- **Production plane (wired):** observes servers, runs detection + governance.
- **Management plane (WiFi):** operators reach the dashboard; never touches production traffic.
- **Sensor plane (ESP32):** physical indicators + tamper tripwires.

```
                      ┌──────────────────────────────────────────────┐
                      │              PRODUCTION LAN                  │
                      │            192.168.100.0/24                  │
                      │                                             │
   Servers ──eth──▶   │   .10+  monitored hosts                     │
   (.10 … .x)         │      │ span/mirror / scan targets           │
                      │      ▼                                      │
                      │   ┌────────┐     ┌────────┐    ┌────────┐   │
                      │   │  Pi4   │     │  Pi3a  │    │  Pi3b  │   │
                      │   │ Brain  │◀───▶│ Attack │    │  IDS   │   │
                      │   │  .1    │     │  .2    │    │  .3    │   │
                      │   └────┬───┘     └───┬────┘    └───┬────┘   │
                      │        │ MQTT        │             │        │
                      │        ▼             ▼             ▼        │
                      │   Mosquitto bus (ultron/#)                  │
                      └──────────────────────┬───────────────────────┘
                                             │
              ┌──────────────────────────────┼──────────────────────────────┐
              │ USB serial                   │ GPIO sense                  │ WiFi (mgmt)
              ▼                              ▼                              ▼
        ┌───────────┐                 ┌─────────────┐              ┌────────────────┐
        │ ESP32-C3  │                 │ ESP32-WROOM │              │ Operator laptop│
        │ NeoPixel  │                 │ Tripwire    │              │ SENTINEL-SECURE│
        │ + OLED    │                 │ + buzzer    │              │ 192.168.50.0/24│
        └───────────┘                 └─────────────┘              └────────────────┘
```

---

## 2. Dual-Network Isolation

| Property | Production LAN | Management LAN |
|----------|----------------|----------------|
| Subnet | `192.168.100.0/24` | `192.168.50.0/24` |
| Medium | Ethernet (5-port switch) | WiFi (`SENTINEL-SECURE`, AC600 on Pi3b) |
| Carries | Scan traffic, IDS taps, MQTT, SSH mgmt | Dashboard HTTP/WebSocket only |
| Exposure | Servers + 3 nodes | Operator devices only |
| Compromise impact | Monitoring continues (fail-visible) | Dashboard access lost only |

**Why:** an attacker on the guest/management WiFi cannot sniff production monitoring. The dashboard is the *only* intentionally reachable service across planes, and it is read-mostly (acknowledgements write back over the same authenticated path).

**Firewall defaults (all Pi nodes):**

```
# fail-closed baseline
INPUT   DROP
OUTPUT  ACCEPT          # nodes initiate outbound
# allow: established, lo, SSH from mgmt, Pi4:8080 from mgmt
# Pi4:   1883/tcp (MQTT) only from 192.168.100.0/24
```

---

## 3. Node Deep-Dives

### 3.1 Pi4 — Brain (`192.168.100.1`)

| Service | Tech | In | Out | Failure mode |
|---------|------|----|-----|--------------|
| `mosquitto` | Mosquitto | TCP 1883 | — | health check restarts; dashboard shows `MQTT DEGRADED` |
| `sentinel-risk` | Python | `ultron/*` events | `ultron/risk/score`, `ultron/risk/band` (retained) | last score held; decay timer logs gaps |
| `sentinel-scan` | Python + nmap/Nuclei/Lynis | cron/timer | `ultron/scan/#`, SQLite | next cycle retries; partial results kept |
| `sentinel-alert` | Python | `ultron/alert/#`, risk bands | SQLite, SMTP, WebSocket, serial → ESP32-C3 | queue on disk; email failures retried 3× |
| `sentinel-dashboard` | Python (aiohttp/fastapi) + static `index.html` | WS from MQTT | browser :8080 | page serves last-known; banner `LIVE/DEGRADED` |
| `sentinel-report` | Python | SQLite | `reports/*.md` daily | missed run caught up once |
| `sentinel-heal` | Python + systemd | unit states | restart actions, `ultron/health` | itself supervised by systemd |

**Datastore:** single SQLite file (`~/ultron/ultron.db`) — events, scores, scans, acks, reports index. WAL mode. Nightly `.backup`.

### 3.2 Pi3a — Attack / Deception (`192.168.100.2`)

| Service | Role | Egress topic |
|---------|------|--------------|
| Cowrie | SSH/Telnet honeypot (22/23), JSON logs | `ultron/cowrie/#` |
| auditd + canary bridge | watches planted files | `ultron/canary/#` |
| Web lure | decoy login, logs POSTs | `ultron/lure/#` |
| TL-WN722N | monitor mode (**LAB only**) | `ultron/wifi/#` (LAB) |
| GPIO listener | ESP32-WROOM sense → Pi | `ultron/tripwire/pi3a` |

**Deception principles:** banners look real, sessions are fully scripted, no shell escapes, disk logs rotated daily and mirrored to Pi4 evidence vault.

### 3.3 Pi3b — IDS / Gateway (`192.168.100.3`)

| Service | Role | Notes |
|---------|------|-------|
| Suricata | signature IDS | ET-Open rules; `eve.json` → aggregator |
| `sentinel-agg` | normalize + publish | dedupe by signature+src within 60s window |
| hostapd | `SENTINEL-SECURE` AP | WPA2, mgmt plane only |
| dnsmasq | DHCP + DNS for mgmt | static lease for operator laptop |
| GPIO listener | enclosure sense | `ultron/tripwire/pi3b` |

**IDS placement options (pick at deploy):**

1. **Mirror/span** of server switch port (passive, zero inline risk) — *default for demo*.
2. **Inline** between switch and servers (blocks, but becomes SPOF) — Phase 2 consideration.

### 3.4 ESP32-C3 — Indicator Node

```
Pi4 (JSON @10Hz USB serial) ──▶ ESP32-C3 ──┬──▶ WS2812B ring (8 px)
                                            └──▶ SSD1306 OLED 128×64
```

Serial frame: `{"score":42,"band":"YELLOW","nodes":4,"last":"2026-09-23T12:00:00Z"}` + `\n`.

Firmware rules: non-blocking `NeoPixel.show()` loop, band state machine with hysteresis (1-sample) to prevent flicker at 29/30 boundary, OLED refresh ≤4 Hz.

### 3.5 ESP32-WROOM — Tripwire Node

```
Case switch Pi3a ──GPIO16──▶ (pull-up, LOW = opened)
Case switch Pi3b ──GPIO17──▶
Buzzer        ◀──GPIO4──── Pi-side alarm pattern (or local firmware tone)
```

- **No WiFi** on this node — physical only, so it cannot be remotely disarmed.
- Debounce 50ms; publish edge events (open/close), not levels.
- Alarm pattern mirrors risk band (steady / double / continuous).

---

## 4. Event Pipeline (End-to-End)

```
[Sensor] → MQTT publish → [Broker :1883] → fan-out
                                │
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
         sentinel-risk    sentinel-alert    sentinel-dashboard
         (fusion/score)   (persist/email)   (WS → browser)
                │               │                │
                ▼               ▼                ▼
        risk/band retained  SQLite + SMTP   DOM update <100ms
                │               │
                └───────┬───────┘
                        ▼
              serial → ESP32-C3 → LED + OLED (physical echo)
```

**Latency budget (Phase 1 target):**

| Hop | Budget |
|-----|--------|
| Detection → MQTT publish | ≤ 20 ms |
| Broker → risk engine | ≤ 10 ms |
| Score → band + alert | ≤ 10 ms |
| Alert → WebSocket frame | ≤ 20 ms |
| Frame → DOM paint | ≤ 40 ms |
| **Total event → screen** | **≤ 100 ms** |

---

## 5. Governance Model (Risk Engine)

### 5.1 Signals & Weights

| # | Signal | MQTT source | Weight |
|---|--------|-------------|--------|
| 1 | Canary events | `ultron/canary/#` | 0.25 |
| 2 | Suricata alerts | `ultron/suricata/#` | 0.20 |
| 3 | Scanner findings | `ultron/scan/#` | 0.15 |
| 4 | IDS / aggregated | `ultron/suricata/#` (sev-scaled) | 0.15 |
| 5 | Tripwire | `ultron/tripwire/#` | 0.15 |
| 6 | Behavioral anomalies | `ultron/behavior/#` | 0.10 |

Component scores are each normalized 0–100 (severity maps, count saturates), then:

```
score = clamp(0, 100, Σ component_i × weight_i)
```

### 5.2 Temporal Dynamics

- **Decay:** −2 points every 10 s toward baseline (0), applied when no new input.
- **Rise:** immediate on event (weight × severity).
- **Band hysteresis:** must cross boundary with +2 margin to change band (reduces flapping).

### 5.3 Bands & Escalation (Phase 1 = notify only)

| Band | Range | LED | Dashboard | Email | Phase 2+ (future) |
|------|-------|-----|-----------|-------|-------------------|
| GREEN | 0–29 | breathe | calm | — | — |
| YELLOW | 30–59 | chase | highlight | — | faster scan cadence |
| RED | 60–84 | strobe | alarm | ✓ | nftables drop src |
| PURPLE | 85–100 | pulse | critical + buzzer | ✓ | quarantine host/VLAN |

Phase 1 **never auto-blocks** — it observes, scores, and alerts (demo safety + Black Hat scope).

---

## 6. MQTT Topic Contract

| Topic | Publisher | Subscriber(s) | Retained | Payload sketch |
|-------|-----------|---------------|----------|----------------|
| `ultron/canary/#` | Pi3a | risk, alert | no | `{file,user,ip,t}` |
| `ultron/cowrie/#` | Pi3a | risk, alert | no | `{session,ip,attempt,cmd}` |
| `ultron/lure/#` | Pi3a | risk, alert | no | `{ip,post,ua}` |
| `ultron/suricata/#` | Pi3b | risk, alert | no | `{sig_id,sev,src,dst}` |
| `ultron/scan/#` | Pi4 | risk, alert | no | `{host,port,cve,tool}` |
| `ultron/tripwire/pi3a` | Pi3a | risk, alert | no | `{edge:"open"/"close"}` |
| `ultron/tripwire/pi3b` | Pi3b | risk, alert | no | `{edge:"open"/"close"}` |
| `ultron/risk/score` | Pi4 | all, dash, ESP | **yes** | `42` |
| `ultron/risk/band` | Pi4 | all, dash, ESP | **yes** | `"YELLOW"` |
| `ultron/alert/#` | Pi4 | dash, mailer | no | `{id,sev,title,ts,ack:false}` |
| `ultron/ack/#` | dash | alert svc | no | `{alert_id,op,ts}` |
| `ultron/health/#` | all | Pi4, dash | yes | `{node,up,services[]}` |

QoS: `risk/*` and `health/*` = 1 (retained); event streams = 0; `alert/#` = 1.

---

## 7. Security Architecture

| Layer | Control |
|-------|---------|
| Perimeter | fail-closed iptables/nftables; default DROP inbound |
| SSH | key-only, no root password login, mgmt-plane source allow |
| MQTT | username/password per client; topic ACLs (only Pi4 writes `risk/#`) |
| Dashboard | bind `0.0.0.0:8080` on mgmt path; token or basic auth for acks (Phase 1.5 hardening) |
| Evidence | append-only daily logs on SSD; Pi4 mirror; hashes in report |
| Deception | honeypot/lure never hold real secrets |
| Supply | offline apt mirrors optional; no telemetry |

**Threat notes:** ESP32-WROOM has no radio → tamper path is physically requiring case access *and* is watched. Management WiFi WPA2 + unique PSK rotated per engagement.

---

## 8. Deployment Topology & Power

```
[Power strip 15W adapter]──Pi4
                         ──Pi3a
                         ──Pi3b
[USB 5V hub]──SSD, AC600, TL-WN722N, fan, ESP32s

[5-port switch]──Pi4.eth0, Pi3a.eth0, Pi3b.eth0, uplink/span
```

| Node | RAM | Typical draw | Image |
|------|-----|--------------|-------|
| Pi4 8GB | 8 GB | ~15 W | Pi OS Lite 64-bit |
| Pi3a/b 1 GB | 1 GB | ~5 W each | Pi OS Lite 32-bit |
| ESP32 ×2 | 520 KB | <0.5 W | PlatformIO firmware |
| **Total** | | **~38 W** | |

Storage: 500GB USB SSD (ext4, `noatime`) mounted `/mnt/ultron-evidence`.

---

## 9. Service Lifecycle (systemd)

Every long-running component ships a unit in `systemd/`:

```
sentinel-mqtt.timer / mosquitto.service
sentinel-risk.service      Restart=always RestartSec=5
sentinel-scan.timer        OnCalendar=*:0/15
sentinel-alert.service
sentinel-dashboard.service
sentinel-report.timer      OnCalendar=daily
sentinel-heal.service      checks others every 30s
```

`sentinel-heal` escalation: restart → 30s → restart → 60s → mark `DEGRADED` on health topic → email operator (still Phase 1 alerting, not autonomous response).

---

## 10. Data Model (SQLite core)

```sql
events(id, ts, node, topic, severity, raw_json)
scores(id, ts, score, band, breakdown_json)      -- every change
scans(id, ts, tool, target, findings_json)
alerts(id, ts, sev, title, body, ack_by, ack_ts)
health(node, ts, up, services_json)
reports(path, ts, range_start, range_end)
```

Indexes: `events(ts)`, `scores(ts, band)`, `alerts(ack_by)`.

---

## 11. Phase Roadmap vs Architecture

| Phase | Architectural delta |
|-------|---------------------|
| **1 (now)** | Detection + governance + alerting + premium dashboard; LED/OLED echo |
| **2** | New `sentinel-response` on Pi4; nftables zone manager; reversible playbooks keyed to band crossings; response audit table |
| **3** | New `sentinel-hunt` workers; per-host behavioral baselines; correlation graph; hypothesis scheduler (nmap/Nuclei bursts) |
| **ULTRON-X** | Jetson joins as optional analytics subscriber on same MQTT contract (no schema break) |

**Invariant across phases:** dual planes, ESP32 sensor roles, MQTT topic contract, SQLite evidence chain.

---

## 12. Failure Modes & Responses

| Failure | Detection | System behavior |
|---------|-----------|-----------------|
| One Pi down | missed `health` >30s | dashboard node tile red; risk engine ignores missing sources (weight renormalize); heal attempts |
| MQTT down | connect fail | local services buffer 1000 events RAM, retry; dashboard `MQTT DEGRADED` |
| SSD unmounted | mount check in heal | alerts still RAM+email; report notes `EVIDENCE DEGRADED` |
| ESP32-C3 unplugged | serial EOF | dashboard continues; banner `INDICATOR LINK LOST` |
| Band flap | hysteresis | +2 margin; alert dedupe 60s per sig+src |

---

## 13. Build Order (dependency graph)

```
[1] Network + OS images + firewall DROP baseline
        │
[2] Mosquitto + ACLs  ────────────────┐
        │                             │
[3] health + ack loop                 │
        │                             │
[4] Suricata eve → agg → MQTT         │
[5] Cowrie + canary → MQTT            │
[6] tripwire GPIO listeners           │
        │                             │
[7] risk engine (fusion + bands) ◀────┘
        │
[8] alert manager (SQLite + email)
        │
[9] dashboard (WS + UI)  ← see dashboard.md
        │
[10] ESP32-C3 serial echo + ESP32-WROOM firmware
        │
[11] report timer + evidence mount
        │
[12] LAB mode extras (leaderboard, TL-WN722N)
```

---

## 14. Document Sync Rules

- Hardware/IP/topic changes → update **this file** + `promt.md` §2/§6 in the **same commit**.
- UI/UX changes → `dashboard.md`.
- Scope/phase changes → `blackhat.md` roadmap + `README.md` roadmap.
- Never edit `ULTRON(SEN3)/` (frozen backup, gitignored).
