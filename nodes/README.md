# ULTRON node services

The software that runs on the three Raspberry Pis. Each node is a small,
single-purpose process that talks only MQTT, so any one of them can be
restarted, replaced or compromised without the others losing the plot.

The dashboard is a *view*. These are the appliance.

## Roles

| Node | Address | Process | Job |
|---|---|---|---|
| Pi4 | `192.168.100.1` | `pi4/risk_engine.py` | Fuse every signal into one 0–100 score, drive the shelf indicator |
| Pi3a | `192.168.100.2` | `pi3a/suricata_tail.py` | Forward Suricata IDS alerts |
| Pi3a | `192.168.100.2` | `pi3a/lan_watch.py` | Notice endpoints the operator has not blessed |
| Pi3a | `192.168.100.2` | `pi3a/wifi_monitor.py` | Listen for rogue access points |
| Pi3a | `192.168.100.2` | `pi3a/tripwire_reader.py` | Read the case reed switch assembly |
| Pi3b | `192.168.100.3` | `pi3b/alert_manager.py` | Own the evidence vault, own acknowledgement, send mail |

`common/ultron.py` holds the contract they all share: band thresholds, risk
weights, topic names, and the MQTT wrapper. Nothing restates a threshold
locally — `tests/test_ultron_contract.py` fails the build if a node and the
risk engine ever disagree about what `RED` means.

## Signals and topics

| Topic | Published by | Payload |
|---|---|---|
| `ultron/suricata/<sig_id>` | Pi3a | signature, severity, src/dest IP |
| `ultron/lan/<mac>` | Pi3a | mac, ip, vendor, known, first/last seen |
| `ultron/wifi/<bssid>` | Pi3a | bssid, ssid, channel, severity |
| `ultron/tripwire/<node>` | Pi3a | node, edge, open, open count |
| `ultron/health/<node>` | every node | node, up, services |
| `ultron/risk/score` | Pi4 | `{"v": 0..100}` |
| `ultron/risk/band` | Pi4 | `{"b": GREEN\|YELLOW\|RED\|PURPLE}` |
| `ultron/alert/<id>` | Pi4 / Pi3b | id, ts, sev, title, src, body, ack |
| `ultron/ack/<id>` | dashboard | acknowledgement from the operator |

Weights: Suricata `0.40`, tripwire `0.30`, WiFi `0.20`, LAN `0.10`.
Bands: `GREEN < 30 ≤ YELLOW < 60 ≤ RED < 85 ≤ PURPLE`.

## Running a node

```bash
# Pi4 - risk engine + shelf indicator
python pi4/risk_engine.py --serial /dev/ttyACM0
python pi4/risk_engine.py --no-serial          # no indicator attached
python pi4/risk_engine.py --selftest           # 25 checks, no broker needed

# Pi3a - detection
python pi3a/suricata_tail.py --eve /var/log/suricata/eve.json
python pi3a/lan_watch.py --interface eth0 --state /var/lib/ultron/lan.json
python pi3a/wifi_monitor.py --interface wlan1 --trusted SENTINEL-SECURE
python pi3a/tripwire_reader.py --serial /dev/ttyUSB0 --node pi3a

# Pi3b - alert manager (the only writer of the vault)
python pi3b/alert_manager.py --db /mnt/pendrive/ultron/ultron.db --dry-run
```

All of them accept `--mqtt-host` / `--mqtt-port` / `--user` / `--pass`.

### Exercising the pipeline without hardware

Every collector has a `--replay` path that emits one synthetic event and exits.
This is the supported way to check a wiring change end to end before the case
is closed:

```bash
python pi3a/lan_watch.py --replay        # one unfamiliar endpoint
python pi3a/wifi_monitor.py --replay     # one evil-twin access point
python pi3a/suricata_tail.py --replay    # one ET SCAN alert
python pi3a/tripwire_reader.py --replay  # one open/close pair
python pi4/risk_engine.py --selftest     # scoring maths, no broker required
```

`--replay` deliberately never touches the state ledger, so it runs anywhere —
including on a machine that cannot write `/var/lib/ultron`.

## The two ESP32s

**`firmware/esp32-wroom-tripwire`** — case reed switches.
`GPIO16` reed in (Pi3a), `GPIO17` reed in (Pi3b), `GPIO18`/`GPIO19` out to the
Pis, `GPIO2` heartbeat. Active-low by design, so a cut wire reads as **open**
rather than as safe. It never calls `WiFi.begin()`: there is no remote path to
disarm it, and the absence of its heartbeat is itself an alarm.

**`firmware/esp32-c3-indicator`** — the shelf display.
SSD1306 OLED on I2C `SDA 8` / `SCL 9` (`0x3C`), optional WS2812B on `GPIO10`,
USB to Pi4 USB 2.0 at `115200`. Renders the score and the band **as a word**,
because colour alone is not accessible and a photograph of the shelf should
still be readable. If the link goes quiet for 3 s it shows `LINK LOST` instead
of freezing on the last good number — an honest blank beats a confident lie.

## Design decisions worth defending

**No detector scores its own findings.** `suricata_tail.py` forwards; only the
risk engine weighs. A detector that grades its own work can be argued out of
its conclusions.

**One writer for the evidence vault.** Only Pi3b appends. Every other node —
and the dashboard — opens it read-only. A compromised detection node therefore
cannot delete the alert that names it.

**Acknowledgement is durable, not optimistic.** The dashboard ACKs, Pi3b writes
`ack`/`ack_ts` and re-publishes the stored record, and only then does the UI
settle. The operator sees the record, not their own hope.

**Failures point at alarm, not at calm.** Active-low reeds, a dead-man heartbeat
on the tripwire link, and `LINK LOST` on the indicator all mean the quiet
failure mode is a false alarm, never a missed one.

## Deploying

```
/opt/ultron/
├── venv/                 # python + paho-mqtt (+ pyserial on Pi3a)
├── nodes/                # this tree
└── dashboard/
/etc/ultron/alert.env     # ULTRON_SMTP_HOST / _USER / _PASS / MAIL_TO
/var/lib/ultron/          # per-node state ledgers
/mnt/pendrive/ultron/     # evidence vault (Pi3b writes, everyone reads)
```

Units live in `systemd/`. They run as `ultron`, with `ProtectSystem=strict`,
`NoNewPrivileges`, `PrivateTmp` and a `DeviceAllow` scoped to the serial device
each one actually needs:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl enable --now ultron-risk-engine ultron-alert-manager \
    ultron-suricata-tail ultron-lan-watch ultron-tripwire-reader \
    ultron-wifi-monitor
```

Adjust `--serial`, `--interface` and `--eve` for your hardware before enabling.
