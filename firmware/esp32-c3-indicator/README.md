# ESP32-C3 — indicator

Renders the risk score on an SSD1306 OLED and tint an optional WS2812B strip.
Connected to Pi4 over USB 2.0 at 115200, reading newline-delimited JSON.

## Pins

| Pin | Destination | Protocol |
|-----|-------------|----------|
| USB | Pi4 USB **2.0** | 115200, newline JSON, ~10 Hz — also the board's power |
| GPIO8 | SSD1306 SDA | I2C |
| GPIO9 | SSD1306 SCL | I2C, address `0x3C` |
| **3V3** | SSD1306 VCC | power — **3.3 V, not 5 V** (see Wiring) |
| GPIO10 | WS2812B DIN | single-wire NRZ (optional) |
| **5V** | WS2812B VCC | power (optional strip) |
| GND | OLED + strip | common ground |

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

The strip follows the same rule, off the same check: with the link down it
breathes amber rather than holding the last band colour. A green strip sitting
above a panel that says `LINK LOST` is the one combination this board must never
show, so both outputs read the same `link_lost()`.

## What the panel shows

| Region | Content |
|--------|---------|
| top | risk score, large |
| middle | band as an **inverted word banner** — `GREEN` `YELLOW` `RED` `PURPLE` |
| lower | `msg`, cut to one line with a trailing `~` when it does not fit |
| bottom right | `N OPEN`, shown only when something is unacknowledged |

Colour alone carries no information to a colour-blind operator and none at all
in a photograph of the shelf, which is why the band is a word as well as a tint.

## Wiring: what goes on 5 V and what does not

- **Board — 5 V**, from the Pi4's USB 2.0 port, over the same cable that carries
  the data.
- **OLED — 3V3, not 5 V.** SSD1306 breakouts tie their I2C pull-ups to the
  module's `VCC` pin, so a 5 V `VCC` pulls SDA and SCL toward 5 V while the
  ESP32-C3's pins are 3.3 V parts. That is out of spec and is a real way to lose
  a GPIO. The module's own regulator runs happily from 3.3 V, so 5 V buys
  nothing here.
- **WS2812B strip — 5 V**, which is what it is specified for. Its data line is
  still driven at 3.3 V logic, the usual marginal case that works in practice at
  these lengths, and `LED_BRIGHT = 40` keeps the current draw small.
- **An unidentified band renders `----` in grey, never green.** The band arrives
  from another machine over a wire; a value of `red` or `RED ` used to fall
  through to the healthy colour.

## Why no radio

There is no WiFi and there is deliberately no `WiFi.begin()` to add one. The
link to Pi4 is the USB cable — one-directional, with nothing to say back. A
wireless indicator is a second way to be lied to, and adding a radio would put a
remote path to a display whose whole job is to be trusted.

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
