---
name: Bug report
about: Something behaves incorrectly
title: "[bug] "
labels: bug
---

## What happens

<!-- The behaviour you observed. -->

## What you expected

## How to reproduce

```
# the exact commands
```

## Environment

- Component: `dashboard` / `nodes` / `firmware` / `start.sh`
- ULTRON version: `curl -s localhost:8080/healthz | python3 -m json.tool`
- Node host details (if a Pi service): model, OS
- Firmware board (if ESP32): board and `pio` version

## Evidence

Relevant log lines. For a Pi service: `journalctl -u ultron-<name> -n 50`.
For the dashboard: `/tmp/ultron-server.log` if launched via `start.sh`.

## Have you confirmed this is not expected behaviour?

Phase 1 is notify-only — ULTRON does not block or remediate. That is by design,
not a bug. See `docs`/`README` and `SECURITY.md`.

- [ ] This is not the intended notify-only behaviour

## Security

If this is a security issue, **stop** and report it privately per `SECURITY.md`
instead of filing here.
