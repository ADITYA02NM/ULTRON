// ULTRON — ESP32-C3 indicator, wireless link (TEMPLATE).
//
// Copy this file to secrets.h in the same directory and fill in your own
// network:
//
//   cp include/secrets.example.h include/secrets.h
//
// secrets.h is gitignored. Credentials must never be committed, and they must
// never be put in config.h, which is tracked.
//
// With no secrets.h present the board builds as a pure USB-serial display and
// never starts the radio. That is still the default and it still works.

#pragma once

// ── WiFi ────────────────────────────────────────────────────────────────────
#define ULTRON_WIFI_SSID "your-network"
#define ULTRON_WIFI_PASS "your-passphrase"

// ── MQTT ────────────────────────────────────────────────────────────────────
// The broker as seen *from the board* — i.e. the machine running start.sh, not
// localhost. start.sh's mosquitto listens on 0.0.0.0:1883 and allows anonymous
// clients, so no credentials are needed for the local demo rig.
#define ULTRON_MQTT_HOST "192.168.1.10"
#define ULTRON_MQTT_PORT 1883
