// ULTRON — ESP32-C3 indicator.
//
// Physical role: the visible state of the appliance. Pi4 (governance) writes
// newline-delimited JSON down the USB 2.0 link; this board renders the score,
// the band, the fleet and the response state.
//
// The link is one-directional and the board never scores anything itself. If
// the link goes quiet the panel says LINK LOST rather than freezing on a stale
// number — a stale GREEN is worse than an honest blank, because it tells the
// operator the house is fine when nobody is actually watching.
//
// Input contract, one JSON object per line (~10 Hz):
//   {"score": 38, "band": "YELLOW", "open": 0, "msg": "IP camera probed"}
//   score  0-100 int      band  GREEN|YELLOW|RED|PURPLE
//   open   unacked alerts msg   optional one-line tail (<=60 chars at source)
//
// Transport: USB serial is always live. If include/secrets.h is present the
// board additionally subscribes to the broker, so the same panel can be driven
// with no cable attached. All feeds land in apply_line()/apply_score()/
// apply_band() and all of them stamp last_rx, so link_lost() does not care
// which transport is carrying the data — and a dead radio cannot poison the
// cable.
//
// The panel mirrors the fleet, not just the score: `ultron/health/<node>` is a
// retained heartbeat, so the four boxes along the bottom are filled only while
// that node is actually reporting. A box is a fact, not decoration.
//
// The pixel carries colour AND motion, taken from the reference firmware
// (../voidmain/firmware/esp32-risk-mini):
//   GREEN  throb   — normal, being watched
//   YELLOW blink   — something is being probed
//   RED    blink   — alert
//   PURPLE throb   — lockdown / acting
//   no link: blue throb. A steady colour alone cannot distinguish "quiet" from
//   "shouting", which is why motion is not optional here.
//
// Consistency notes, since "the panel sometimes looks wrong" is the bug report
// this file keeps attracting:
//   * the panel and the pixel share one link_lost() predicate, so they can
//     never disagree about whether the Pi is talking. The pixel used to keep
//     glowing the last band colour while the panel said LINK LOST.
//   * an unrecognised band is its own state, not GREEN. The band arrives from
//     another machine over a wire; collapsing "red" or "RED " into green is
//     how a red alert ends up painting a healthy indicator.
//   * the panel is only repainted when what it shows has actually changed.
//     Redrawing 4x/second regardless is what makes an OLED look restless.
//   * the score is printed "%3d", so it does not slide sideways as digits are
//     added and removed.

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoPixel.h>
#include <ArduinoJson.h>

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "config.h"

#if defined(ULTRON_HAS_WIFI)
#include <WiFi.h>
#include <PubSubClient.h>
#endif

namespace {

Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);
Adafruit_NeoPixel pixel(LED_COUNT, PIN_LED_DATA, NEO_GRB + NEO_KHZ800);
bool strip_ok = false;

// What the pixel is doing right now. The panel spells this word out, so the two
// outputs are describing one state rather than two guesses at it.
enum class LedMode : uint8_t { Offline, Normal, Detect, Alert, Action };
LedMode led_mode = LedMode::Offline;

// The fleet that actually reports. Each box is filled only while that node's
// retained health message says up, so an empty box means silence, not "fine".
const char *const NODES[4] = {"pi4", "pi3a", "pi3b", "esp32"};
bool node_up[4] = {false, false, false, false};

// The four bands plus an explicit unknown. Keep the unknown: a silent fallback
// to green is the single most dangerous thing this board could do.
enum class Band : uint8_t { Green, Yellow, Red, Purple, Unknown };

struct Reading {
  int score = 0;
  Band band = Band::Unknown;
  int open = 0;
  char msg[64] = "";
  bool have_data = false;
  uint32_t last_rx = 0;
};

Reading g;
String line;

// A frame longer than this is not something the Pi sends, so it is a line
// getting out of step rather than data. Drop it instead of trusting it.
constexpr size_t MAX_FRAME = 256;

// One line at text size 1 is 6 px per glyph across 128 px.
constexpr size_t MSG_COLS = OLED_W / 6;

const char *band_name(Band b) {
  switch (b) {
    case Band::Green:  return "GREEN";
    case Band::Yellow: return "YELLOW";
    case Band::Red:    return "RED";
    case Band::Purple: return "PURPLE";
    default:           return "----";
  }
}

// Exact band rails in 0xRRGGBB, the same values the reference firmware uses.
// They are deliberately not "close enough": brightening or desaturating a red
// rail is how an operator ends up reading red as amber on a cheap pixel.
constexpr uint32_t pack_rgb(uint8_t r, uint8_t g, uint8_t b) {
  return (static_cast<uint32_t>(r) << 16) | (static_cast<uint32_t>(g) << 8) | b;
}
// Fully saturated rails, one channel left at zero in each so nothing can wash
// toward white. Muted mixes are easier on a desk but fail on a shelf: a red
// that leans brown and a green that leans teal make the operator stop and
// decode the colour instead of reading the band. Red is red, green is green,
// purple is purple, and the gap between them is the whole signal.
constexpr uint32_t RGB_GREEN  = pack_rgb(0x00, 0xff, 0x00);
constexpr uint32_t RGB_YELLOW = pack_rgb(0xff, 0xcc, 0x00);
constexpr uint32_t RGB_RED    = pack_rgb(0xff, 0x00, 0x00);
constexpr uint32_t RGB_PURPLE = pack_rgb(0xb0, 0x00, 0xff);
constexpr uint32_t RGB_BLUE   = pack_rgb(0x00, 0x40, 0xff);  // no link / connecting

uint32_t band_colour(Band b) {
  switch (b) {
    case Band::Green:  return RGB_GREEN;
    case Band::Yellow: return RGB_YELLOW;
    case Band::Red:    return RGB_RED;
    case Band::Purple: return RGB_PURPLE;
    default:           return RGB_BLUE;   // "I do not know" is not green
  }
}

// Uppercase and trim before comparing, so a wire value of "red" or "RED " is
// still understood as RED rather than falling through to the default.
Band parse_band(const char *raw) {
  if (raw == nullptr) return Band::Unknown;
  char buf[12];
  size_t n = 0;
  while (raw[n] != '\0' && n < sizeof(buf) - 1) {
    buf[n] = static_cast<char>(toupper(static_cast<unsigned char>(raw[n])));
    n++;
  }
  while (n > 0 && (buf[n - 1] == ' ' || buf[n - 1] == '\t')) n--;
  buf[n] = '\0';

  if (strcmp(buf, "GREEN") == 0)  return Band::Green;
  if (strcmp(buf, "YELLOW") == 0) return Band::Yellow;
  if (strcmp(buf, "RED") == 0)    return Band::Red;
  if (strcmp(buf, "PURPLE") == 0) return Band::Purple;
  return Band::Unknown;
}

// The one place that decides whether the Pi is still talking. Both the panel
// and the pixel read this, so the two outputs cannot contradict each other.
bool link_lost() {
  if (!g.have_data) return true;
  return (millis() - g.last_rx) > LINK_TIMEOUT_MS;
}

// Keeps a message to the one line it is documented to be, marking a cut with
// a tilde rather than letting the print wrap and run off the bottom edge.
void fit_msg(char *out, size_t out_len, const char *src) {
  if (out_len == 0) return;
  const size_t room = (MSG_COLS < out_len - 1) ? MSG_COLS : out_len - 1;
  size_t n = strlen(src);
  if (n > room) n = room;
  memcpy(out, src, n);
  out[n] = '\0';
  if (strlen(src) > room && room >= 2) out[room - 1] = '~';
}

void apply_line(const String &raw) {
  JsonDocument doc;
  const DeserializationError err = deserializeJson(doc, raw);
  if (err) return;                                  // keep the last good reading

  g.score = doc["score"] | g.score;

  // Only a present-but-unrecognised band becomes Unknown. A frame that simply
  // omits the field should not blank the band we are already showing.
  if (doc["band"].is<const char *>()) g.band = parse_band(doc["band"].as<const char *>());

  g.open = doc["open"] | 0;

  const char *msg = doc["msg"].as<const char *>();
  strncpy(g.msg, msg ? msg : "", sizeof(g.msg) - 1);   // bounded: another machine
  g.msg[sizeof(g.msg) - 1] = '\0';

  g.have_data = true;
  g.last_rx = millis();

  // One line a second at most. Without it a fed panel and a merely powered one
  // look identical from this end of the cable, and the only debugger is a person
  // standing in front of the shelf.
  static uint32_t last_frame_log = 0;
  if (millis() - last_frame_log >= 1000) {
    last_frame_log = millis();
    Serial.printf("[frame] score=%d open=%d\n", g.score, g.open);
  }
}

// The dashboard's separate score and band topics. Handled as well as the full
// frame because that is what today's feeds publish — a wireless board should
// light up without anyone having to invent a new topic first.
void apply_score(const String &raw) {
  JsonDocument doc;
  if (deserializeJson(doc, raw)) return;
  if (!doc["v"].is<int>()) return;
  g.score = doc["v"].as<int>();
  g.have_data = true;
  g.last_rx = millis();
}

void apply_band(const String &raw) {
  JsonDocument doc;
  if (deserializeJson(doc, raw)) return;
  if (!doc["b"].is<const char *>()) return;
  g.band = parse_band(doc["b"].as<const char *>());
  g.have_data = true;
  g.last_rx = millis();
}

// Retained `ultron/health/<node>`. `up` is a heartbeat age in seconds, so zero
// means the node is silent rather than merely idle.
void apply_health(const char *leaf, const String &raw) {
  JsonDocument doc;
  if (deserializeJson(doc, raw)) return;
  const bool up = (doc["up"] | 0) > 0;
  for (size_t i = 0; i < 4; i++) {
    if (strcmp(leaf, NODES[i]) == 0) {
      node_up[i] = up;
      return;
    }
  }
}

#if defined(ULTRON_HAS_WIFI)
WiFiClient net;
PubSubClient mqtt(net);
uint32_t next_wifi_try = 0;
uint32_t next_mqtt_try = 0;
bool wifi_was_up = false;

// Which transport is actually feeding the panel. The serial port is listening
// either way, so USB is the honest answer when the broker is not connected.
const char *transport_word() { return mqtt.connected() ? "MQTT" : "USB"; }

void on_mqtt(char *topic, byte *payload, unsigned int len) {
  // Bytes with no terminator and no length contract we control. Copy into a
  // bounded buffer and NUL it rather than trusting the broker.
  if (len >= MAX_FRAME) return;
  char buf[MAX_FRAME];
  memcpy(buf, payload, len);
  buf[len] = '\0';
  const String body(buf);

  if (strcmp(topic, ULTRON_TOPIC_FRAME) == 0)       apply_line(body);
  else if (strcmp(topic, ULTRON_TOPIC_SCORE) == 0) apply_score(body);
  else if (strcmp(topic, ULTRON_TOPIC_BAND) == 0)  apply_band(body);
  else if (strncmp(topic, "ultron/health/", 14) == 0) apply_health(topic + 14, body);
}

// Deliberately non-blocking. A broker that never answers must not freeze a
// panel whose whole job is to keep showing the truth, and the serial path has
// to keep working while the radio retries.
void net_begin() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // mains-powered: latency matters, power does not
  WiFi.begin(ULTRON_WIFI_SSID, ULTRON_WIFI_PASS);
  Serial.println("[net] wifi join requested");
}

void net_loop(uint32_t now) {
  const bool wifi_up = (WiFi.status() == WL_CONNECTED);
  if (wifi_up != wifi_was_up) {
    wifi_was_up = wifi_up;
    if (wifi_up) Serial.printf("[wifi] up, ip=%s\n", WiFi.localIP().toString().c_str());
    else         Serial.println("[wifi] down, retrying");
  }
  if (!wifi_up) {
    if (static_cast<int32_t>(now - next_wifi_try) < 0) return;
    next_wifi_try = now + 10000;
    WiFi.reconnect();
    return;
  }
  if (!mqtt.connected()) {
    if (static_cast<int32_t>(now - next_mqtt_try) < 0) return;
    next_mqtt_try = now + 5000;
    // A dead broker should cost a couple of seconds, not the library default.
    net.setTimeout(2);
    mqtt.setSocketTimeout(2);
    String id = "ultron-c3-";
    id += String(static_cast<uint32_t>(ESP.getEfuseMac()), HEX);
    if (!mqtt.connect(id.c_str())) {
      Serial.printf("[mqtt] connect failed rc=%d\n", mqtt.state());
      return;
    }
    mqtt.subscribe(ULTRON_TOPIC_FRAME);
    mqtt.subscribe(ULTRON_TOPIC_SCORE);
    mqtt.subscribe(ULTRON_TOPIC_BAND);
    mqtt.subscribe(ULTRON_TOPIC_HEALTH);
    Serial.printf("[mqtt] up -> %s:%u\n", ULTRON_MQTT_HOST,
                  static_cast<unsigned>(ULTRON_MQTT_PORT));
    return;
  }
  mqtt.loop();
}
#else
const char *transport_word() { return "USB"; }
void net_begin() {}
void net_loop(uint32_t) {}
#endif

// Everything the panel currently shows, as a compact string. Comparing this
// against what was last drawn is what stops the panel being repainted four
// times a second when nothing has moved.
void screen_sig(char *out, size_t n) {
  if (!g.have_data) {
    snprintf(out, n, "NODATA|%s", transport_word());
  } else if (link_lost()) {
    snprintf(out, n, "LOST|%lu|%s",
             static_cast<unsigned long>((millis() - g.last_rx) / 1000), transport_word());
  } else {
    snprintf(out, n, "OK|%d|%d|%d|%s|%s|%d%d%d%d", g.score, static_cast<int>(g.band), g.open,
             g.msg, transport_word(), node_up[0], node_up[1], node_up[2], node_up[3]);
  }
}

// ── the pixel ────────────────────────────────────────────────────────────────

LedMode mode_for(bool lost, Band b) {
  if (lost) return LedMode::Offline;
  switch (b) {
    case Band::Green:  return LedMode::Normal;
    case Band::Yellow: return LedMode::Detect;
    case Band::Red:    return LedMode::Alert;
    case Band::Purple: return LedMode::Action;
    default:           return LedMode::Offline;
  }
}

// How fast the pixel toggles between the full rail and off. 0 means no motion.
uint16_t mode_period_ms(LedMode m) {
  switch (m) {
    case LedMode::Normal: return 0;      // all clear: a steady green lamp
    case LedMode::Detect: return 500;    // 2 Hz yellow
    case LedMode::Alert:  return 250;    // 4 Hz red -- the one that must not be missed
    case LedMode::Action: return 1000;   // 1 Hz purple
    default:              return 2000;   // 0.5 Hz blue while there is no link
  }
}

uint32_t mode_colour(LedMode m) {
  switch (m) {
    case LedMode::Normal: return RGB_GREEN;
    case LedMode::Detect: return RGB_YELLOW;
    case LedMode::Alert:  return RGB_RED;
    case LedMode::Action: return RGB_PURPLE;
    default:              return RGB_BLUE;
  }
}

// Motion here is two-level on purpose. Every colour is a full-intensity rail --
// green is 0x00ff00, red is 0xff0000, purple is 0xb000ff -- and none of them is
// ever dimmed. A dimmed rail is a *different* colour: pull a saturated red down
// and it reads as brown, not as a darker red, and anything halfway between two
// rails reads as a mix nobody asked for. The contrast comes from the pixel being
// fully on or fully off, never from a brightness ramp.
void led_loop() {
  led_mode = mode_for(link_lost(), g.band);
  if (!strip_ok) return;

  const uint32_t now = millis();
  const uint16_t period = mode_period_ms(led_mode);
  // period == 0 means no motion at all: an all-clear is a steady green lamp.
  const bool lit = period == 0 || ((now / (period / 2)) & 1) != 0;

  const uint32_t rail = mode_colour(led_mode);
  const uint32_t want = lit ? rail : 0u;

  // NeoPixel writes are interrupt-disabled, so do not push an identical frame
  // every few microseconds just because the loop ran again.
  static uint32_t shown = 0xFFFFFFFFu;
  if (want == shown) return;
  shown = want;

  for (uint16_t i = 0; i < LED_COUNT; i++) pixel.setPixelColor(i, want);
  pixel.show();
}

// ── the panel ────────────────────────────────────────────────────────────────

float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

// One eye, taken from the reference firmware: a ring, a pupil that can look
// sideways, and lids that can close. open_amt 0 = shut, 1 = wide.
void draw_eye(int cx, int cy, int r, float open_amt, float look_x) {
  if (open_amt <= 0.03f) {
    oled.drawLine(cx - r, cy, cx + r, cy, SSD1306_WHITE);
    return;
  }
  oled.drawCircle(cx, cy, r, SSD1306_WHITE);
  const int pr = r / 3;
  const int px = cx + static_cast<int>(look_x * (r - pr - 3));
  oled.fillCircle(px, cy, pr, SSD1306_WHITE);
  if (open_amt < 0.97f) {
    const int half = static_cast<int>(r * open_amt);
    oled.fillRect(cx - r - 2, cy - r - 2, 2 * r + 4, r - half + 2, SSD1306_BLACK);
    oled.fillRect(cx - r - 2, cy + half, 2 * r + 4, r - half + 2, SSD1306_BLACK);
    oled.drawLine(cx - r, cy - half, cx + r, cy - half, SSD1306_WHITE);
    oled.drawLine(cx - r, cy + half, cx + r, cy + half, SSD1306_WHITE);
  }
}

// An eye that reads as happy rather than shut: the same arc the lid draws, but
// curving upward, so the opening is above it and it reads as ^ rather than as a
// closed eye.
void draw_happy_eye(int cx, int cy, int r) {
  for (int x = -r; x <= r; x++) {
    const float s = static_cast<float>(r * r - x * x);
    const int y = static_cast<int>(sqrtf(s) * 0.55f);
    oled.writePixel(cx + x, cy - y - 3, SSD1306_WHITE);
    oled.writePixel(cx + x, cy - y - 2, SSD1306_WHITE);
  }
}

// A wide grin: high at the corners, low in the middle.
void draw_smile(int cx, int cy, int half, int depth) {
  for (int x = -half; x <= half; x++) {
    const float u = static_cast<float>(x) / static_cast<float>(half);
    const int y = static_cast<int>(static_cast<float>(depth) * (1.0f - u * u));
    oled.writePixel(cx + x, cy + y, SSD1306_WHITE);
    oled.writePixel(cx + x, cy + y + 1, SSD1306_WHITE);
  }
}

// Boot, in three beats: the eyes open, the eyes close, and then the character
// smiles for three seconds before the readout takes over. The pixel pulses blue
// underneath the whole time, so a board that is awake but has never heard from
// anything is distinguishable at a glance from a dead one.
void boot_animation() {
  constexpr uint32_t T_OPEN = 900, T_CLOSE = 700, T_SMILE = 3000;
  constexpr uint32_t T_TOTAL = T_OPEN + T_CLOSE + T_SMILE;
  constexpr int cy = 30, R = 15, cxA = 40, cxB = 88;
  const uint32_t t0 = millis();
  Serial.println("[boot] eyes");

  while (millis() - t0 < T_TOTAL) {
    const uint32_t e = millis() - t0;

    oled.clearDisplay();
    oled.setTextColor(SSD1306_WHITE);
    oled.setTextSize(1);
    oled.setCursor(46, 2);
    oled.print(F("ULTRON"));

    if (e < T_OPEN) {
      // Lids lifting. Squared, so it snaps open rather than crawling.
      const float p = static_cast<float>(e) / T_OPEN;
      draw_eye(cxA, cy, R, p * p, 0.0f);
      draw_eye(cxB, cy, R, p * p, 0.0f);
    } else if (e < T_OPEN + T_CLOSE) {
      // And coming back down again.
      const float p = static_cast<float>(e - T_OPEN) / T_CLOSE;
      const float open_amt = 1.0f - p * p;
      draw_eye(cxA, cy, R, open_amt, 0.0f);
      draw_eye(cxB, cy, R, open_amt, 0.0f);
    } else {
      // Three seconds is long enough to register and short enough not to hold
      // up a demo.
      draw_happy_eye(cxA, cy, R);
      draw_happy_eye(cxB, cy, R);
      draw_smile(OLED_W / 2, 46, 26, 8);
    }

    oled.display();
    led_loop();
    delay(15);
  }
  Serial.println("[boot] smile");
}

// A shallow arc opening downward: the sleeping eyelid. The same character as the
// boot animation, just asleep.
void draw_lid(int cx, int cy, int r) {
  for (int x = -r; x <= r; x++) {
    const float s = static_cast<float>(r * r - x * x);
    const int y = static_cast<int>(sqrtf(s) * 0.6f);
    oled.writePixel(cx + x, cy - y, SSD1306_WHITE);
    oled.writePixel(cx + x, cy - y + 1, SSD1306_WHITE);
  }
}

// Awake but not being told anything. Rather than a bare "no signal", the same
// character that booted is now asleep: drooping lids, a couple of drifting Zs and
// one plain-English caption. It reads as the board waiting rather than as the
// board being broken, which is a distinction an operator makes in half a second.
void draw_lost() {
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(46, 2);
  oled.print(F("ULTRON"));

  draw_lid(40, 36, 15);
  draw_lid(88, 36, 15);

  oled.setCursor(108, 14);
  oled.print(F("z"));
  oled.setCursor(118, 8);
  oled.print(F("z"));

  const char *cap = g.have_data ? "asleep - no signal" : "waiting for data";
  oled.setCursor((OLED_W - static_cast<int16_t>(strlen(cap)) * 6) / 2, 54);
  oled.print(cap);
}

// Four boxes down the left-hand corner: filled = that node is reporting,
// outlined = it is not (or has not said anything yet). The same highlight the
// dashboard uses for its own fleet readout, so the shelf and the console agree
// box for box instead of telling two different stories.
void draw_nodes(int16_t y0) {
  constexpr int16_t boxW = 38, boxH = 11, gap = 2;
  constexpr int16_t x0 = 0;

  oled.setTextSize(1);
  for (size_t i = 0; i < 4; i++) {
    const int16_t y = y0 + static_cast<int16_t>(i) * (boxH + gap);
    if (node_up[i]) {
      oled.fillRect(x0, y, boxW, boxH, SSD1306_WHITE);
      oled.setTextColor(SSD1306_BLACK);
    } else {
      oled.drawRect(x0, y, boxW, boxH, SSD1306_WHITE);
      oled.setTextColor(SSD1306_WHITE);
    }
    oled.setCursor(x0 + 4, y + 2);
    oled.print(NODES[i]);
    oled.setTextColor(SSD1306_WHITE);
  }
}

const char *status_word(LedMode m) {
  switch (m) {
    case LedMode::Alert:  return "ALERT";
    case LedMode::Detect: return "DETECT";
    case LedMode::Action: return "LOCKDOWN";
    case LedMode::Normal: return "NORMAL";
    default:              return "OFFLINE";
  }
}

void draw() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);

  if (link_lost()) {
    draw_lost();
    oled.display();
    return;
  }

  // Heading, then a hairline to separate it from the readout.
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print(F("ULTRON"));
  oled.drawLine(0, 10, OLED_W - 1, 10, SSD1306_WHITE);

  // The fleet, stacked down the left-hand corner.
  draw_nodes(14);

  // The score, on the right and at an ordinary size. Fixed width, so it does
  // not slide sideways between 9 and 100.
  char sb[8];
  snprintf(sb, sizeof(sb), "%3d", g.score);
  oled.setTextSize(3);
  oled.setCursor(OLED_W - 3 * 18 - 2, 18);
  oled.print(sb);

  // The band, as a word in an inverted box under the score: the same colour the
  // LED is showing, spelled out for anyone who cannot tell the colours apart and
  // for anyone looking at a photograph of the shelf afterwards.
  const char *bn = band_name(g.band);
  const int16_t bw = static_cast<int16_t>(strlen(bn)) * 6 + 8;
  const int16_t bx = OLED_W - bw;
  oled.fillRect(bx, 46, bw, 13, SSD1306_WHITE);
  oled.setTextColor(SSD1306_BLACK);
  oled.setCursor(bx + 4, 49);
  oled.print(bn);
  oled.setTextColor(SSD1306_WHITE);

  oled.display();
}

// Bring the panel up on the I2C pair that is actually soldered, and on whichever
// address answers. Adapted from the working reference firmware: this project had
// only ever tried one pair at one address, so a differently wired header
// produced a permanently blank screen with no diagnosis.
bool oled_begin() {
  static const uint8_t pairs[][2] = {
      {PIN_I2C_SDA, PIN_I2C_SCL},
  };

  for (size_t p = 0; p < sizeof(pairs) / sizeof(pairs[0]); p++) {
    Wire.begin(pairs[p][0], pairs[p][1]);
    delay(20);   // let the bus settle before the first probe

    uint8_t addr = 0;
    for (uint8_t a = OLED_ADDR; a <= OLED_ADDR + 1; a++) {
      Wire.beginTransmission(a);
      if (Wire.endTransmission() == 0) { addr = a; break; }
    }
    if (addr == 0) {
      // Nothing on the usual addresses. Sweep, so an unusual module is found
      // rather than silently written off.
      for (uint8_t a = 0x08; a < 0x78; a++) {
        Wire.beginTransmission(a);
        if (Wire.endTransmission() == 0) { addr = a; break; }
      }
    }
    if (addr == 0) {
      Serial.printf("[oled] nothing on sda=%u scl=%u\n", pairs[p][0], pairs[p][1]);
      Wire.end();
      continue;
    }

    if (oled.begin(SSD1306_SWITCHCAPVCC, addr)) {
      Serial.printf("[oled] up: sda=%u scl=%u addr=0x%02X\n",
                    pairs[p][0], pairs[p][1], addr);
      return true;
    }
    Serial.printf("[oled] 0x%02X answered on sda=%u scl=%u but init failed\n",
                  addr, pairs[p][0], pairs[p][1]);
    Wire.end();
  }

  Serial.println("[oled] no panel on any candidate pair");
  return false;
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.setTimeout(50);

  // The pixel comes up before the panel so the boot animation can pulse it.
  pixel.begin();
  pixel.setBrightness(LED_BRIGHT);
  pixel.clear();
  pixel.show();
  strip_ok = true;

  if (oled_begin()) {
    // Never let a print reflow onto a second line; the layout is fixed and a
    // wrapped line would push text past the bottom edge.
    oled.setTextWrap(false);
    boot_animation();
  }

  line.reserve(MAX_FRAME);

#if defined(ULTRON_HAS_WIFI)
  mqtt.setServer(ULTRON_MQTT_HOST, ULTRON_MQTT_PORT);
  mqtt.setCallback(on_mqtt);
  mqtt.setBufferSize(384);   // a full frame plus its topic must fit
  net_begin();
#endif
}

void loop() {
  while (Serial.available() > 0) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      if (line.length() > 0) apply_line(line);
      line = "";
      continue;
    }
    if (line.length() >= MAX_FRAME) {   // out of step, not data
      line = "";
      continue;
    }
    line += c;
  }

  net_loop(millis());

  // The pixel runs at loop speed so its throb is smooth; only the panel is
  // capped at 4 Hz, because that is what the display can take without smearing.
  led_loop();

  // Signed difference, so this does not stall when millis() rolls over.
  static uint32_t next_draw = 0;
  if (static_cast<int32_t>(millis() - next_draw) < 0) return;
  next_draw = millis() + REDRAW_MS;

  static char shown_sig[96] = "";
  char sig[96];
  screen_sig(sig, sizeof(sig));
  if (strcmp(sig, shown_sig) != 0) {
    strncpy(shown_sig, sig, sizeof(shown_sig) - 1);
    shown_sig[sizeof(shown_sig) - 1] = '\0';
    draw();
  }
}
