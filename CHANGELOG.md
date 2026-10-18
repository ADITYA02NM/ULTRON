# Changelog

All notable changes to ULTRON are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Phase 1 is **notify-only**: ULTRON observes and reports, and does not act on the
network. Response and remediation are Phase 2.

## [Unreleased]

### Changed

- **Relicensed to Apache-2.0**, from MIT. Apache-2.0 grants a patent licence
  explicitly (§3) and states that no trademark rights are conveyed (§6). MIT is
  silent on both, and that silence is what slows adoption of security tooling by
  organisations that would otherwise deploy it. `NOTICE` now carries the
  attribution text the licence expects (§4).

### Added

- **`THIRD_PARTY.md`** — the third-party licence inventory that was missing
  entirely. It carries the four font copyright notices, the full SIL Open Font
  License 1.1 text, the Python and Node dependency licences, and the boundary
  that matters most: Suricata, mosquitto and nftables are **invoked as separate
  processes**, never linked against or redistributed, so their copyleft licences
  do not reach this source. The dashboard self-hosts four OFL typefaces and was
  serving them with no notice at all — anyone redistributing a built dashboard
  or a booth image had no right to pass those fonts on.
- **`SECURITY.md` → "Security boundaries"** — trust zones, a per-component table
  of what each board is trusted for and what it can do if compromised (the
  architectural claim being that no node both decides and records), an explicit
  list of what the appliance does **not** defend against, the authorisation
  boundary that applies to passive wireless and LAN monitoring, and the residual
  risk accepted on purpose.
- **`dashboard/web/package.json`** — gained `license` (it had none, which reads
  as all-rights-reserved to every tool that asks) and `engines.node >= 20`.
- **Animated startup mark** on the lock screen (`BootMark.tsx`): the risk engine
  at the centre of the mesh, a detection wave leaving the core, and the watched
  nodes reporting in turn. CSS keyframes, so the existing
  `prefers-reduced-motion` rule disables it for free.

### Fixed

- **Credential revocation did not end the sessions it authorised.** Revoking a
  passkey revoked a row and nothing else: live sessions kept working for the
  remainder of their TTL, and an open WebSocket was never re-checked. Sessions
  are now refused once their credential is revoked, the endpoint closes the
  affected sockets and reports the count, and sockets re-validate every 20 s.
- **No Origin check on state-changing requests.** `POST /auth/skip` needs no
  cookie to mint a session, so any page could have submitted a form to it.
  POST/PUT/PATCH/DELETE now require a configured `Origin`.
- The rate-limit table no longer grows without bound, and a rejected request is
  audited once per window instead of writing a row per attempt.
- The demo access code is 128 bits rather than 32; verification failures return a
  generic message; the debug basic-auth comparison is constant-time;
  `auth.db` and `.demo-code` are `0600`.
- The demo-rig section of `SECURITY.md` said "Two behaviours" and listed three.

### Security

- 17 new regression tests across `test_session_lifecycle.py` and
  `test_hardening.py`. Backend 50 → 67 passing.

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
