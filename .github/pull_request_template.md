## What this changes

<!-- One paragraph. What problem, and why this approach. -->

## Which layer

- [ ] `dashboard/` (web UI)
- [ ] `dashboard/server/` (backend, auth, bridge)
- [ ] `nodes/` (Pi services)
- [ ] `firmware/` (ESP32)
- [ ] docs / tooling / CI

## Verification

Paste the real output — not "tests pass".

```
cd dashboard && ../.venv/bin/python -m pytest -q
cd .. && .venv/bin/python -m pytest -q nodes/tests
.venv/bin/python nodes/pi4/risk_engine.py --selftest
cd dashboard/web && npm run typecheck && npm run check:tokens && npm run test
```

## Checklist

- [ ] Behaviour changes come with a test that fails without them
- [ ] No threshold or weight is restated outside `nodes/common/ultron.py`
- [ ] No node service gained a network call (the appliance must work offline)
- [ ] No second writer was added to the evidence vault
- [ ] Sensor failure modes still point at alarm, not at calm
- [ ] Hardware code that has not been bench-tested is not described as if it has

## If you touched auth, the MQTT bridge, or the risk engine

Which threat did you consider? Anything security-relevant should go through the
private channel in `SECURITY.md`, not a public issue.
