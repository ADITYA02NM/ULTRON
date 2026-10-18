# Changelog

All notable changes to ULTRON are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Phase 1 is **notify-only**: ULTRON observes and reports, and does not act on the
network. Response and remediation are Phase 2.

## [Unreleased]

## [0.5.0-phase1] — 2026-10-18

### Added

- **Node services** (`nodes/`) — the software for the three Raspberry Pis.
  Previously the project shipped no code for any of the hardware it described.
  - `common/ultron.py` — the shared contract: band thresholds, risk weights,
    topic names and the MQTT wrapper, defined once and imported everywhere.
  - `pi4/risk_engine.py` — fuses every signal into a single 0–100 score and
    drives the shelf indicator.
  - `pi3a/suricata_tail.py` — forwards Suricata `eve.json` IDS alerts.
  - `pi3a/lan_watch.py` — reports endpoints the operator has not blessed.
  - `pi3a/wifi_monitor.py` — listens for rogue access points and evil twins.
  - `pi3a/tripwire_reader.py` — reads the case reed switch assembly.
  - `pi3b/alert_manager.py` — sole writer of the evidence vault, owner of
    acknowledgement, and the only node that sends mail.
  - Six hardened systemd units in `nodes/systemd/`.
- **ESP32 firmware** (`firmware/`) — two PlatformIO projects.
  - `esp32-wroom-tripwire` — active-low case reed switches, radio never
    started, newline-delimited JSON over UART.
  - `esp32-c3-indicator` — SSD1306 shelf display showing the score and the band
    as a word, with `LINK LOST` when the link goes quiet.
- **One-command launcher** (`start.sh`) — starts the broker, the backend, the
  dashboard and a demo feed, then prints an enrolment QR code. `--prod` serves
  the built bundle for phone/second-screen access.
- **LAN demo rig** — a shared access code (`POST /auth/demo`), a skip path
  (`POST /auth/skip`), `ULTRON_ALLOW_LAN` for non-loopback origins, and a
  standalone phone alerts page at `/alerts`. Enables a second screen and a phone
  to join a demonstration without a passkey ceremony. Documented as a known
  exposure in `SECURITY.md`.
- **Token-free first-owner enrolment** from loopback, so a fresh install can
  register its first passkey without a CLI step.
- Repo hygiene: `LICENSE` (MIT), `SECURITY.md`, CI running the backend, node and
  frontend suites on every push.

### Fixed

- **Risk engine: a lone case-open scored GREEN.** `TRIPWIRE_SEVERITY` was `0.9`,
  so an open case scored `100 × 0.30 × 0.9 = 27`, below the YELLOW threshold of
  30 — the appliance could have its own lid prised off while the display read
  all-clear. Now `1.0`. Regression-tested.
- **Risk engine: hysteresis was inverted.** Band thresholds are ordered
  highest-severity-first, so a lower index means a more severe band. The
  comparison made rises wait for a margin and drops happen instantly — the exact
  opposite of intent. Rises are now immediate; drops require clearing the margin.
- **Alert acknowledgement did not stick.** The dashboard dropped repeat alert
  ids, so an acknowledgement re-stamped by the alert node could never update the
  row. A repeat carrying `ack: true` is now treated as an update.
- **The launcher could serve another project's app.** It skipped starting vite
  when port 5173 was busy, then reported "healthy" because *something* answered
  its poll. It now refuses to reuse a port held by a process outside this repo,
  and the dev server runs with `strictPort`.
- `tools/smoke_pi.sh` called removed auth internals; it now uses the supported
  `python -m server.auth_cli enroll-token`.

### Changed

- The browser simulation, the MQTT demo feed and the risk engine now tell the
  same device-wise story. The previous script had everything failing at once;
  the demo now shows ordinary household activity with one real finding.
- Three smart-home endpoints (IP camera, smart plug, door sensor) are modelled
  across the topology, the simulation and the demo feed.
- Signing in and signing out both reset all live dashboard state, so a session
  never inherits the previous operator's view.

## [0.4.0] — prior

Phase 1 dashboard, WebAuthn authentication, MQTT bridge, evidence vault reader,
design system. See git history.
