// ULTRON — ESP32-C3 indicator.
//
// Physical role: the visible state of the appliance. Pi4 (governance) writes
// newline-delimited JSON down the USB 2.0 link; this board renders the score
// as a colour and the band as a word.
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
// Consistency notes, since "the panel sometimes looks wrong" is the bug report
// this file keeps attracting:
//   * the panel and the strip share one link_lost() predicate, so they can
//     never disagree about whether the Pi is talking. The strip used to keep
//     glowing the last band colour while the panel said LINK LOST.
//   * an unrecognised band is its own state, not GREEN. The band arrives from
//     another machine over a wire; collapsing "red" or "RED " into green is
//     how a red alert ends up painting a healthy indicator.
//   * the panel is only repainted when what it shows has actually changed.
//     Redrawing 4x/second regardless is what makes an OLED look restless.

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <FastLED.h>

#include <ctype.h>
#include <stdio.h>

#include "config.h"

namespace {

Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);
CRGB leds[LED_COUNT];
bool leds_ok = false;

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

CRGB band_colour(Band b) {
  switch (b) {
    case Band::Green:  return CRGB(58, 200, 112);
    case Band::Yellow: return CRGB(212, 176, 48);
    case Band::Red:    return CRGB(208, 72, 56);
    case Band::Purple: return CRGB(160, 96, 208);
    default:           return CRGB(140, 140, 140);   // neutral: NOT green
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
// and the strip read this, so the two outputs cannot contradict each other.
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
}

// Everything the panel currently shows, as a compact string. Comparing this
// against what was last drawn is what stops the panel being repainted four
// times a second when nothing has moved.
void screen_sig(char *out, size_t n) {
  if (!g.have_data) {
    snprintf(out, n, "NODATA");
  } else if (link_lost()) {
    snprintf(out, n, "LOST|%lu", static_cast<unsigned long>((millis() - g.last_rx) / 1000));
  } else {
    snprintf(out, n, "OK|%d|%d|%d|%s", g.score, static_cast<int>(g.band), g.open, g.msg);
  }
}

void draw_lost() {
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print(F("ULTRON"));
  oled.setTextSize(2);
  oled.setCursor(0, 16);
  oled.print(F("LINK"));
  oled.setCursor(0, 36);
  oled.print(F("LOST"));

  char tail[24];
  if (!g.have_data) {
    strcpy(tail, "no data yet");
  } else {
    snprintf(tail, sizeof(tail), "silent %lus",
             static_cast<unsigned long>((millis() - g.last_rx) / 1000));
  }
  oled.setTextSize(1);
  oled.setCursor(0, 56);
  oled.print(tail);
}

void draw() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);

  if (link_lost()) {
    draw_lost();
    oled.display();
    return;
  }

  // The number, big.
  oled.setTextSize(3);
  oled.setCursor(0, 0);
  oled.print(g.score);

  // The band as a word, inverted so it carries as much weight as the number.
  // Colour alone is not accessible and a photo of the shelf should still be
  // readable, which is why the band is a word at all.
  const char *bn = band_name(g.band);
  const int16_t bw = static_cast<int16_t>(strlen(bn)) * 12;
  oled.fillRect(0, 26, bw + 4, 18, SSD1306_WHITE);
  oled.setTextColor(SSD1306_BLACK);
  oled.setTextSize(2);
  oled.setCursor(2, 27);
  oled.print(bn);
  oled.setTextColor(SSD1306_WHITE);

  if (g.msg[0] != '\0') {
    char fitted[64];
    fit_msg(fitted, sizeof(fitted), g.msg);
    oled.setTextSize(1);
    oled.setCursor(0, 46);
    oled.print(fitted);
  }

  if (g.open > 0) {
    char buf[16];
    snprintf(buf, sizeof(buf), "%d OPEN", g.open);
    oled.setTextSize(1);
    oled.setCursor(OLED_W - static_cast<int16_t>(strlen(buf)) * 6, 56);
    oled.print(buf);
  }

  oled.display();
}

void paint_leds() {
  if (!leds_ok) return;

  CRGB c;
  if (link_lost()) {
    // Amber, breathing slowly. Unmistakably "not reporting" — and different
    // from both a band colour and a dark strip, since a dead-looking strip and
    // a green strip are lies of two different kinds.
    const uint32_t phase = millis() % 2000;
    const uint8_t ramp = (phase < 1000)
                           ? static_cast<uint8_t>(phase / 20)
                           : static_cast<uint8_t>((2000 - phase) / 20);
    const uint8_t lvl = static_cast<uint8_t>(10 + ramp);
    c = CRGB(lvl, static_cast<uint8_t>(lvl * 3 / 5), 0);
  } else {
    c = band_colour(g.band);
  }

  static CRGB shown = CRGB(0, 0, 0);
  if (c.r == shown.r && c.g == shown.g && c.b == shown.b) return;
  shown = c;

  for (uint8_t i = 0; i < LED_COUNT; i++) leds[i] = c;
  FastLED.show();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.setTimeout(50);

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);

  if (oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    // Never let a print reflow onto a second line; the layout is fixed and a
    // wrapped line would push text past the bottom edge.
    oled.setTextWrap(false);
    oled.clearDisplay();
    oled.setTextColor(SSD1306_WHITE);
    oled.setTextSize(1);
    oled.setCursor(0, 28);
    oled.print(F("ULTRON starting"));
    oled.display();
  }

  FastLED.addLeds<WS2812B, PIN_LED_DATA, GRB>(leds, LED_COUNT);
  FastLED.setBrightness(LED_BRIGHT);
  leds_ok = true;
  fill_solid(leds, LED_COUNT, CRGB::Black);
  FastLED.show();

  line.reserve(MAX_FRAME);
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

  // Drawing is deliberately capped: an OLED redrawn at serial rate smears.
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
  paint_leds();
}
