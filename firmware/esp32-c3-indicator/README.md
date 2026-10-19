# ESP32-C3 — indicator

Renders the risk score on an SSD1306 OLED and shows the band on **one onboard
NeoPixel**. No strip, no second display: four things on the glass and one colour
on the LED, so it can be read from across a room.

Connected to Pi4 over USB 2.0 at 115200, reading newline-delimited JSON. It also
speaks MQTT when WiFi credentials are present — see [Transport](#transport).

## Pins

| Pin | Destination | Protocol |
|-----|-------------|----------|
| USB | Pi4 USB **2.0** | 115200, newline JSON — also the board's power |
| GPIO5 | SSD1306 **SDA** | I2C |
| GPIO6 | SSD1306 **SCL** | I2C, address `0x3C` |
| **3V3** | SSD1306 VCC | power — **3.3 V, not 5 V** (see Wiring) |
| GPIO8 | NeoPixel DIN | single-wire NRZ, `LED_COUNT = 1` (the onboard pixel) |
| **5V** | NeoPixel VCC | power — 5 V, which is what it is specified for |
| GND | OLED + LED | common ground |

`GPIO8` carries the pixel, so the I2C pair is fixed to **5/6**. There is no
alternate pair to probe.

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
good reading stands. `score`, `band` and `open` are parsed and validated on the
way in; the panel face below is deliberately only four elements, so `open` and
`msg` currently reach the board but are not drawn. They are logged:

```
[frame] score=31 open=13
```

An unidentified band is **never green**. The band arrives from another machine
over a wire, and a value of `red` or `RED ` used to fall through to the healthy
colour; it now renders as the no-link colour instead.

## Boot

Power-up runs one character beat before the readout appears, the same four moves
every time:

| Beat | What happens |
|------|--------------|
| 800 ms | the lids come up |
| 900 ms | he turns to his left |
| 1000 ms | ...and sweeps slowly across to the right |
| 450 ms | ...and back to the front |
| 2200 ms | the grin, and then the readout takes over |

Nothing slides. Wall-E's eyes are fixed lenses on a head that pivots, so the turn
is drawn as perspective instead: the eye on the side he turns towards swings
round to face you and **grows**, while the far eye foreshortens and **shrinks**.
Two circles changing size in opposite directions read as a head turning without a
single pupil ever leaving the centre of its eye.

The pixel pulses blue throughout, so a board that is awake but has never heard
from anything looks different at a glance from a dead one. The log says
`[boot] eyes` when it starts and `[boot] wall-e` when it hands over.

## What the panel shows

| Region | Content |
|--------|---------|
| top | heading `ULTRON`, with a hairline under it |
| **left corner** | the fleet: four boxes, `pi4` `pi3a` `pi3b` `esp32` — filled when that node is reporting, outlined when it is not |
| **right** | the risk score, three digits, fixed width so it does not slide between `9` and `100` |
| bottom right | the band as an **inverted word** — `GREEN` `YELLOW` `RED` `PURPLE` |

The four fleet boxes are fed by `ultron/health/<node>` and follow the same
highlight the dashboard uses, so the shelf and the console agree box for box.

Colour alone carries no information to a colour-blind operator and none at all in
a photograph of the shelf, which is why the band is a word as well as a tint.

## Why it goes to sleep

If the link goes quiet for **3 s** the panel stops showing the score and draws a
**sleeping face** — eyes shut, `Z`s drifting off, and the caption
`asleep - no signal` (or `waiting for data` before the first frame ever arrives).

The LED follows the same rule, off the same `link_lost()` check: with no link it
blinks the no-link colour rather than holding the last band colour. A green pixel
sitting above a panel that has gone to sleep is the one combination this board
must never show, so both outputs read the same predicate.

Freezing on the last number would mean the shelf keeps displaying a stale
**GREEN** while nothing is watching the house. An honest sleep beats a confident
lie.

## What the LED means

Five colours, **full rail or off** — there is no dimming and no brightness ramp,
so `LED_BRIGHT` does not wash the hue out. Motion is the only signal:

| Band / state | Colour | Motion |
|--------------|--------|--------|
| `GREEN` | `0x00ff00` | **steady** — on continuously |
| `YELLOW` | `0xffcc00` | 2 Hz hard blink |
| `RED` | `0xff0000` | 4 Hz hard blink |
| `PURPLE` | `0xb000ff` | 1 Hz slow blink |
| no link, or unknown band | `0x0040ff` | 0.5 Hz slow blink |

Each colour is a pure rail, so green reads green and red reads red — no teal
shift from mixing channels down toward grey.

## Wiring: what goes on 5 V and what does not

- **Board — 5 V**, from the Pi4's USB 2.0 port, over the same cable that carries
  the data.
- **OLED — 3V3, not 5 V.** SSD1306 breakouts tie their I2C pull-ups to the
  module's `VCC` pin, so a 5 V `VCC` pulls SDA and SCL toward 5 V while the
  ESP32-C3's pins are 3.3 V parts. That is out of spec and is a real way to lose
  a GPIO. The module's own regulator runs happily from 3.3 V, so 5 V buys
  nothing here.
- **NeoPixel — 5 V**, which is what it is specified for. Its data line is driven
  at 3.3 V logic, the usual marginal case that works in practice for a single
  onboard pixel.

## Transport

Two transports, one contract:

- **USB — always.** The board reads newline JSON on its serial port and nothing
  is needed to enable it.
- **MQTT — when `include/secrets.h` exists.** Drop the file in and the board also
  joins WiFi, subscribes to the topic set below, and takes its frames from there.
  Without the file the firmware still builds; the WiFi code is compiled out.

`include/secrets.h` is gitignored because it holds the WiFi passphrase. Copy
`include/secrets.example.h` to `include/secrets.h` and fill it in.

| Topic | Payload |
|-------|---------|
| `ultron/risk/frame` | the whole frame above |
| `ultron/risk/score` | `{"v": 38}` |
| `ultron/risk/band` | `{"b": "YELLOW"}` |
| `ultron/health/#` | `{"node": "pi4", "up": 5390, "services": ["ok"]}` — `up > 0` means reporting |

On the demo rig the local access point is **5 GHz** and the ESP32-C3 is
**2.4 GHz-only**, so the board cannot associate with it at all. USB is the
transport that actually works there, and it is why the board is cabled rather
than on the radio.

## Why no scoring on-board

Two independent scorers eventually disagree, and then the operator has to decide
which display to believe. Pi4 is the single source of truth; this board only
renders. Nothing on this board reads a sensor, weighs anything, or decides a
band — which is also why a dropped frame is a reason to go to sleep and never a
reason to guess.

## Build

```bash
cd firmware/esp32-c3-indicator
pio run                                              # compile
pio run --target upload --upload-port /dev/ttyUSB0   # flash
pio device monitor                                   # watch the boot log
```

Only one process may hold the serial port. If the upload cannot open it, check
with `lsof /dev/ttyUSB0` — a running serial bridge will be holding it.
