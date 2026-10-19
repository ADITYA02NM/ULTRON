// ULTRON — ESP32-C3 indicator board configuration.
//
// The board is a dumb display: it renders whatever the governance node tells
// it. It performs no scoring of its own, on purpose — two independent scorers
// would eventually disagree and the operator would not know which to believe.

#pragma once

#include <Arduino.h>

// ── I2C / OLED ───────────────────────────────────────────────────────────────
// One pair, and an address that is probed rather than assumed. 5/6 is what the
// working ESP32-C3 SuperMini reference project (../voidmain/firmware/
// esp32-risk-mini) drives its panel on. The old 8/9 fallback is gone on purpose:
// GPIO8 now carries the NeoPixel, and probing an I2C bus on the LED data line
// would make the pixel flicker garbage on a mis-wired board.
constexpr uint8_t  PIN_I2C_SDA  = 5;
constexpr uint8_t  PIN_I2C_SCL  = 6;
constexpr uint8_t  OLED_ADDR    = 0x3C;
constexpr uint8_t  OLED_W       = 128;
constexpr uint8_t  OLED_H       = 64;

// ── NeoPixel ─────────────────────────────────────────────────────────────────
// GPIO8 is the onboard WS2812 on the ESP32-C3 SuperMini, and the same pin the
// reference project drives. LED_COUNT = 1 is that single onboard pixel; raise
// it if an external strip is wired to the same data line.
constexpr uint8_t  PIN_LED_DATA = 8;
constexpr uint8_t  LED_COUNT    = 1;
constexpr uint8_t  LED_BRIGHT   = 255;  // full rail: colours are never dimmed

// Colour names the band; motion says what is being done about it. The pixel is
// driven at the full rail or fully off, and the timings live with led_loop() in
// main.cpp because they are part of the motion, not of the wiring.

// ── Serial link to Pi4 (USB 2.0) ─────────────────────────────────────────────
constexpr uint32_t SERIAL_BAUD   = 115200;
constexpr uint32_t LINK_TIMEOUT_MS = 3000;  // silence => show LINK LOST

// Drawing is deliberately capped: an OLED redrawn at serial rate smears, and
// the documented limit is <=4 Hz.
constexpr uint32_t REDRAW_MS = 250;

// ── Optional wireless link ───────────────────────────────────────────────────
// The board is still a USB-serial display first: the cable is never disabled.
// If include/secrets.h exists it ALSO mirrors the same data off the broker, so
// it can stand on a shelf with no host attached. With no secrets.h the radio is
// never started at all, which is the default build.
#if defined(__has_include)
#if __has_include("secrets.h")
#include "secrets.h"
#define ULTRON_HAS_WIFI 1
#endif
#endif

// Topics the dashboard already publishes. The board understands all of them:
// `frame` carries the whole panel, `score`/`band` are what the existing feeds
// send, and `health/#` is the fleet's retained heartbeat behind the four boxes.
constexpr char ULTRON_TOPIC_FRAME[]  = "ultron/risk/frame";
constexpr char ULTRON_TOPIC_SCORE[]  = "ultron/risk/score";
constexpr char ULTRON_TOPIC_BAND[]   = "ultron/risk/band";
constexpr char ULTRON_TOPIC_HEALTH[] = "ultron/health/#";
