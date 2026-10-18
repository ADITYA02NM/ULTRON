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
//   open   unacked alerts msg   optional one-line tail

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <FastLED.h>

#include "config.h"

namespace {

Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);
CRGB leds[LED_COUNT];
bool leds_ok = false;

struct Reading {
  int   score       = 0;
  char  band[12]    = "GREEN";
  int   open        = 0;
  char  msg[64]     = "";
  bool  have_data   = false;
  uint32_t last_rx  = 0;
};

Reading g;
String line;
char last_msg[64] = "";

CRGB band_colour(const char *band) {
  if (strcmp(band, "PURPLE") == 0) return CRGB(160, 96, 208);
  if (strcmp(band, "RED")    == 0) return CRGB(208, 72, 56);
  if (strcmp(band, "YELLOW") == 0) return CRGB(212, 176, 48);
  return CRGB(58, 200, 112);
}

void apply_line(const String &raw) {
  JsonDocument doc;
  const DeserializationError err = deserializeJson(doc, raw);
  if (err) return;                       // keep the last good reading

  g.score = doc["score"] | g.score;
  const char *band = doc["band"] | "GREEN";
  // Copy through a bounded buffer: the field arrives from another machine.
  strncpy(g.band, band, sizeof(g.band) - 1);
  g.band[sizeof(g.band) - 1] = '\0';

  g.open = doc["open"] | 0;
  const char *msg = doc["msg"] | "";
  strncpy(g.msg, msg, sizeof(g.msg) - 1);
  g.msg[sizeof(g.msg) - 1] = '\0';

  g.have_data = true;
  g.last_rx = millis();
}

void draw() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);

  if (!g.have_data || (millis() - g.last_rx) > LINK_TIMEOUT_MS) {
    oled.setTextSize(1);
    oled.setCursor(0, 8);
    oled.println(F("ULTRON"));
    oled.setTextSize(2);
    oled.setCursor(0, 26);
    oled.println(F("LINK"));
    oled.setCursor(0, 46);
    oled.println(F("LOST"));
    oled.display();
    return;
  }

  // Score, large and unmissable.
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print(F("ULTRON  SCORE"));
  oled.setTextSize(3);
  oled.setCursor(0, 12);
  oled.print(g.score);

  // Band as a word: colour alone is not accessible, and a photo of the shelf
  // should still be readable.
  oled.setTextSize(1);
  oled.setCursor(78, 20);
  oled.print(g.band);

  if (g.open > 0) {
    oled.setCursor(78, 32);
    oled.print(g.open);
    oled.print(F(" OPEN"));
  }

  if (g.msg[0]) {
    if (strncmp(g.msg, last_msg, sizeof(last_msg)) != 0) {
      strncpy(last_msg, g.msg, sizeof(last_msg) - 1);
      last_msg[sizeof(last_msg) - 1] = '\0';
    }
    oled.setCursor(0, 48);
    oled.print(last_msg);
  }
  oled.display();
}

void paint_leds() {
  if (!leds_ok) return;
  const CRGB c = band_colour(g.band);
  for (uint8_t i = 0; i < LED_COUNT; i++) leds[i] = c;
  FastLED.show();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.setTimeout(50);

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  if (oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
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

  line.reserve(256);
}

void loop() {
  while (Serial.available()) {
    const char c = (char)Serial.read();
    if (c == '\n') {
      if (line.length()) apply_line(line);
      line = "";
    } else if (c != '\r') {
      if (line.length() < 255) line += c;
      else line = "";   // overlong frame: drop it rather than trust it
    }
  }

  static uint32_t next_draw = 0;
  if (millis() >= next_draw) {
    next_draw = millis() + REDRAW_MS;
    draw();
    paint_leds();
  }
}
