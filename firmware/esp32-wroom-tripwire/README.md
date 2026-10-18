# ESP32-WROOM — tripwire sensor

Reads the Pi3a and Pi3b case reed switches and drives a level back to each Pi.
**The radio is never started.**

## Why a separate MCU

A tripwire that lives on the machine it is protecting is not a tripwire. If the
Pi is compromised, a software tripwire is one `systemctl stop` away from silent.
Here the sensor is a second, dumber device with no network interface at all —
so there is no remote path to disarm it, and its absence is itself an alarm.

## Pins

| Pin | Dir | Destination | Logic |
|-----|-----|-------------|-------|
| GPIO16 | in | Pi3a case reed | pull-up, LOW = open |
| GPIO17 | in | Pi3b case reed | pull-up, LOW = open |
| GPIO18 | out | Pi3a GPIO | mirrors GPIO16 |
| GPIO19 | out | Pi3b GPIO | mirrors GPIO17 |
| GPIO2 | out | heartbeat | 2 ms blip at 1 Hz |
| GND | — | common | — |

Active-low is a security decision: a cut wire reads as **open**, never as
"safe". Failing toward alarm is the correct direction for this sensor.

## Failure semantics

| Observation | Meaning |
|-------------|---------|
| heartbeat present, line idle | sensor alive, case closed |
| heartbeat present, line high | case physically open |
| heartbeat **absent** | sensor unplugged, cut, or dead — treat as tamper |
| line high with reed reading closed | wiring tampered with |

## Build

```bash
cd firmware/esp32-wroom-tripwire
pio run                 # compile
pio run --target upload # flash
pio device monitor      # 115200, newline-delimited JSON
```

No third-party libraries — Arduino core only.
