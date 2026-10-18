# ESP32-C3 — indicator

Renders the risk score on an SSD1306 OLED and tint an optional WS2812B strip.
Connected to Pi4 over USB 2.0 at 115200, reading newline-delimited JSON.

## Pins

| Pin | Destination | Protocol |
|-----|-------------|----------|
| USB | Pi4 USB **2.0** | 115200, newline JSON, ~10 Hz |
| GPIO8 | SSD1306 SDA | I2C |
| GPIO9 | SSD1306 SCL | I2C, address `0x3C` |
| GPIO10 | WS2812B DIN | single-wire NRZ (optional) |
| 5V / GND | Pi4 USB2 | power |

## Input contract

```json
{"score": 38, "band": "YELLOW", "open": 1, "msg": "IP camera probed for default credentials"}
```

| Field | Type | Meaning |
|-------|------|---------|
| `score` | int 0–100 | weighted risk score |
| `band` | string | `GREEN` `YELLOW` `RED` `PURPLE` |
| `open` | int | unacknowledged alerts |
| `msg` | string | optional one-line tail |

Malformed lines and overlong frames are **dropped, not guessed at** — the last
good reading stands.

## Why it shows LINK LOST

If the serial link goes quiet for 3 s the panel stops showing the score and says
`LINK LOST`. Freezing on the last number would mean the shelf keeps displaying
a stale **GREEN** while nothing is watching the house. An honest blank beats a
confident lie.

## Why no scoring on-board

Two independent scorers eventually disagree, and then the operator has to decide
which display to believe. Pi4 is the single source of truth; this board only
renders.

## Build

```bash
cd firmware/esp32-c3-indicator
pio run
pio run --target upload
pio device monitor
```
