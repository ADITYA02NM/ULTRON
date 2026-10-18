// ULTRON — ESP32-C3 indicator board configuration.
//
// The board is a dumb display: it renders whatever the governance node tells
// it. It performs no scoring of its own, on purpose — two independent scorers
// would eventually disagree and the operator would not know which to believe.

#pragma once

#include <Arduino.h>

// ── I2C / OLED ───────────────────────────────────────────────────────────────
constexpr uint8_t  PIN_I2C_SDA = 8;
constexpr uint8_t  PIN_I2C_SCL = 9;
constexpr uint8_t  OLED_ADDR   = 0x3C;
constexpr uint8_t  OLED_W      = 128;
constexpr uint8_t  OLED_H      = 64;

// ── Optional WS2812B 8-pixel strip ───────────────────────────────────────────
constexpr uint8_t  PIN_LED_DATA = 10;
constexpr uint8_t  LED_COUNT    = 8;
constexpr uint8_t  LED_BRIGHT   = 40;   // 0-255; a bar on a shelf, not a torch

// ── Serial link to Pi4 (USB 2.0) ─────────────────────────────────────────────
constexpr uint32_t SERIAL_BAUD   = 115200;
constexpr uint32_t LINK_TIMEOUT_MS = 3000;  // silence => show LINK LOST

// Drawing is deliberately capped: an OLED redrawn at serial rate smears, and
// the documented limit is <=4 Hz.
constexpr uint32_t REDRAW_MS = 250;
