// ULTRON — ESP32-WROOM tripwire sensor.
//
// Physical role: the two Pi cases (Pi3a governance-side and Pi3b alert-side)
// each carry a reed switch. This board reads both and drives a level back to
// the Pi it belongs to. The radio is never started: that is the whole point of
// putting the tripwire on a second MCU. An attacker who owns the Pi has no way
// to silence the sensor remotely, because there is no remote path to it.
//
// Pins (README "ESP32-WROOM tripwire pins", architecture.md §3.6):
//   GPIO16  in   Pi3a case reed   pull-up, LOW = open
//   GPIO17  in   Pi3b case reed   pull-up, LOW = open
//   GPIO18  out  -> Pi3a GPIO     level follows GPIO16
//   GPIO19  out  -> Pi3b GPIO     level follows GPIO17
//   GPIO2   out  heartbeat        blips 1 Hz so the Pi can tell this board
//                                 is still alive and has not been unplugged
//
// The two output lines mirror the reed state. They exist so the Pi does not
// have to read a 3V3 line directly and so a cut jumper is distinguishable from
// a closed case: heartbeat stops => sensor dead, line high while reed says
// open => wiring tampered with.
//
// Active-low is deliberate: a cut wire reads as OPEN, never as "safe".

#include <Arduino.h>

namespace {

constexpr uint8_t PIN_REED_PI3A = 16;
constexpr uint8_t PIN_REED_PI3B = 17;
constexpr uint8_t PIN_OUT_PI3A  = 18;
constexpr uint8_t PIN_OUT_PI3B  = 19;
constexpr uint8_t PIN_HEARTBEAT = 2;

// The Pi cannot see contact chatter usefully and a reed on a case lid bounces
// heavily on close. 50 ms matches the documented behaviour and is short enough
// that a genuinely fast open is still caught.
constexpr uint32_t DEBOUNCE_MS = 50;

constexpr uint32_t HEARTBEAT_MS = 1000;
constexpr uint32_t HEARTBEAT_WIDTH_US = 2000;

struct Debounced {
  uint8_t pin;
  bool stable;        // true = open (the unsafe/interesting state)
  bool raw;
  uint32_t changed_at;
  uint32_t open_count;
};

Debounced pi3a{PIN_REED_PI3A, false, false, 0, 0};
Debounced pi3b{PIN_REED_PI3B, false, false, 0, 0};

// Read a reed as "open?" — active-low, so a LOW pin or a cut wire is open.
bool reed_open(uint8_t pin) { return digitalRead(pin) == LOW; }

void service(Debounced &d, uint32_t now) {
  const bool reading = reed_open(d.pin);
  if (reading != d.raw) {
    d.raw = reading;
    d.changed_at = now;
  }
  if ((now - d.changed_at) >= DEBOUNCE_MS && reading != d.stable) {
    d.stable = reading;
    if (d.stable) {
      d.open_count++;
    }
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);

  pinMode(PIN_REED_PI3A, INPUT_PULLUP);
  pinMode(PIN_REED_PI3B, INPUT_PULLUP);

  pinMode(PIN_OUT_PI3A, OUTPUT);
  pinMode(PIN_OUT_PI3B, OUTPUT);
  pinMode(PIN_HEARTBEAT, OUTPUT);

  // Seed from the pins so a case already open at boot is reported as open,
  // not as a transition we invented.
  pi3a.raw = pi3a.stable = reed_open(PIN_REED_PI3A);
  pi3b.raw = pi3b.stable = reed_open(PIN_REED_PI3B);
  pi3a.changed_at = pi3b.changed_at = millis();

  digitalWrite(PIN_OUT_PI3A, pi3a.stable ? HIGH : LOW);
  digitalWrite(PIN_OUT_PI3B, pi3b.stable ? HIGH : LOW);

  // Deliberately no WiFi.begin(). The radio stays off for the lifetime of the
  // device; there is nothing here for a remote attacker to talk to.
  Serial.println(F("{\"node\":\"wroom\",\"msg\":\"tripwire armed\",\"radio\":\"off\"}"));
}

void loop() {
  const uint32_t now = millis();

  service(pi3a, now);
  service(pi3b, now);

  digitalWrite(PIN_OUT_PI3A, pi3a.stable ? HIGH : LOW);
  digitalWrite(PIN_OUT_PI3B, pi3b.stable ? HIGH : LOW);

  static bool last_a = false;
  static bool last_b = false;
  if (pi3a.stable != last_a) {
    last_a = pi3a.stable;
    Serial.printf("{\"edge\":\"%s\",\"node\":\"pi3a\",\"open\":%s,\"opens\":%lu}\n",
                  pi3a.stable ? "open" : "close",
                  pi3a.stable ? "true" : "false", (unsigned long)pi3a.open_count);
  }
  if (pi3b.stable != last_b) {
    last_b = pi3b.stable;
    Serial.printf("{\"edge\":\"%s\",\"node\":\"pi3b\",\"open\":%s,\"opens\":%lu}\n",
                  pi3b.stable ? "open" : "close",
                  pi3b.stable ? "true" : "false", (unsigned long)pi3b.open_count);
  }

  // Heartbeat: a 2 ms blip every second. If the Pi stops seeing it, the sensor
  // is gone — unplugged, cut, or dead. Absence is an alarm, not silence.
  static uint32_t next_beat = 0;
  if (now >= next_beat) {
    next_beat = now + HEARTBEAT_MS;
    digitalWrite(PIN_HEARTBEAT, HIGH);
    delayMicroseconds(HEARTBEAT_WIDTH_US);
    digitalWrite(PIN_HEARTBEAT, LOW);
  }
}
