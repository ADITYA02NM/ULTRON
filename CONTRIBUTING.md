# Contributing to ULTRON

ULTRON is a zero-cloud smart-home security appliance: detect → govern → alert.
Phase 1 is deliberately **notify-only** — it tells you, it does not act. Keep
that in mind for every change: a contribution that silently blocks something is
out of scope until Phase 2.

## Layout

```
dashboard/          aiohttp backend + React/Vite dashboard
  server/           routes, WebAuthn auth, MQTT bridge, evidence reader
  web/              React 18 + TypeScript + Vite
  tools/mock_feed.py  dev-only: replays a detection scenario over MQTT
  alerts.html       standalone phone alerts page
nodes/              the software that runs on the three Raspberry Pis
  common/           the shared contract (thresholds, weights, topics, MQTT)
  pi4/ pi3a/ pi3b/  one process per job
  systemd/          hardened unit files
firmware/           PlatformIO projects for the two ESP32s
design/             design tokens and specimens
```

## Development setup

Python 3.11+ and Node 20+.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r dashboard/server/requirements.txt
pip install pytest pytest-asyncio paho-mqtt pyserial   # test-only

cd dashboard/web && npm ci && cd ..
```

The dashboard server must run with `dashboard/` as the working directory:

```bash
cd dashboard && ../.venv/bin/python -m server.main
```

An MQTT broker is required for anything end to end. `tools/mosquitto.dev.conf`
is a no-sudo broker config (anonymous, no persistence) for local work:

```bash
mosquitto -c tools/mosquitto.dev.conf
```

`dashboard/tools/mock_feed.py` then replays the full detection scenario — it
stands in for every detection node and the risk engine at once. It is dev-only
and prints a banner saying so.

## Tests

Run all four before opening a pull request. They are independent, and they are
what CI runs.

```bash
cd dashboard && ../.venv/bin/python -m pytest -q       # backend
cd .. && .venv/bin/python -m pytest -q nodes/tests     # node services
.venv/bin/python nodes/pi4/risk_engine.py --selftest   # scoring maths
cd dashboard/web && npm run typecheck && npm run check:tokens && npm run test
```

`npm run check:tokens` enforces the design system: no raw hex, `rgb()`, `px` or
`ms` outside the documented exceptions. If it fails, add a token instead of a
literal.

## Hardware is not required to run the tests

Every collector has a `--replay` flag that emits one synthetic event and exits,
and the risk engine has `--selftest`. These are the supported way to check a
wiring change without the case open:

```bash
python nodes/pi3a/lan_watch.py --replay
python nodes/pi3a/wifi_monitor.py --replay
python nodes/pi3a/suricata_tail.py --replay
python nodes/pi3a/tripwire_reader.py --replay
python nodes/pi4/risk_engine.py --selftest
```

Please do not add network calls to a node service. The appliance must work with
the internet unplugged, so vendor names come from a local OUI table and nothing
phones home. A detection path that reaches the network is a detection path that
can be watched.

## Changing a threshold or a weight

Band thresholds and risk weights live in **one** place: `nodes/common/ultron.py`.
The dashboard and the risk engine both import them. `nodes/tests/test_ultron_contract.py`
fails the build if they drift apart — if the shelf indicator and the dashboard
disagree about what RED means, the operator has no way to tell which to believe.

Do not restate a threshold locally. If you need a new one, add it to the contract
and let the test hold you to it.

## House rules

- **No detector scores its own findings.** Detectors forward; only the risk
  engine weighs. A detector that grades its own work can be argued out of its
  conclusions.
- **The evidence vault has exactly one writer** (Pi3b). Everything else opens it
  read-only. Do not add a second writer.
- **Failures point at alarm, not at calm.** Active-low reed switches, a dead-man
  heartbeat on the tripwire link, `LINK LOST` on the indicator. When in doubt
  about a sensor's failure mode, choose the one that produces a false alarm.
- **Do not invent evidence.** If hardware code is written but not bench-tested,
  say exactly that. A fabricated test log is worse than an untested commit.

## Pull requests

Small, single-purpose, with the test output pasted in. If you touched the auth
surface, the MQTT bridge, or the risk engine, say which threat you considered.
See `SECURITY.md` for the current posture and the known demo-rig exposures.

For anything security-relevant, do not open a public issue — use the private
advisory channel described in `SECURITY.md`.
