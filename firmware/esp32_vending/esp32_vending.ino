/**
 * Flower Vending Machine - ESP32 Controller Firmware v2.0
 *
 * Hardware:
 *   RELAY1 (GPIO16) - Door / DRV8833 IN1
 *   RELAY2 (GPIO17) - Cooling relay
 *   RELAY3 (GPIO18) - Spare
 *   RELAY4 (GPIO19) - Drum motor (frequency inverter REV)
 *   BUTTON_PIN (GPIO25) - Service door button (INPUT_PULLUP)
 *   DRUM_ENC (GPIO26) - AS5045 PWM input (drum position)
 *   TEMP_PIN (GPIO34) - DS18B20 temperature sensor (ADC)
 *   LED_PIN (GPIO2) - Status LED
 *
 * Protocol (115200 baud, ASCII, \\n terminated):
 *   DOOR_OPEN    -> OK
 *   DOOR_CLOSE   -> OK
 *   MOTOR_ON     -> OK
 *   MOTOR_OFF    -> OK
 *   VEND_SLOT N  -> OK / ERR (N=1-6)
 *   STATUS       -> OK DOOR=OPEN|CLOSED MOTOR=ON|OFF BUTTON=ON|OFF DRUM=N TEMP=C HOME=N
 *   HOME         -> OK
 *   ENC_CALIBRATE -> OK
 *   TEMP         -> OK TEMP=<celsius>
 *   PINO N [ms]  -> OK
 *   RELAY N ON|OFF -> OK
 *   COOL_ON      -> OK (enable cooling relay)
 *   COOL_OFF     -> OK (disable cooling relay)
 *   INFO         -> OK ESP32_VENDING FIRMWARE v2.0
 *   ALL_OFF      -> OK
 *
 * Errors: ERR UNKNOWN_CMD, ERR HOMING_FAILED, ERR RANGE
 */

#include <OneWire.h>
#include <DallasTemperature.h>

const int RELAY1 = 16;
const int RELAY2 = 17;
const int RELAY3 = 18;
const int RELAY4 = 19;
const int BUTTON_PIN = 25;
const int DRUM_ENC = 26;
const int TEMP_PIN = 34;
const int LED_PIN = 2;
const int RELAY_ON = LOW;
const int RELAY_OFF = HIGH;
const int PULSE_MS = 700;
const int SERIAL_BAUD = 115200;
const int CMD_TIMEOUT_MS = 100;

// Temperature sensor
OneWire oneWire(TEMP_PIN);
DallasTemperature sensors(&oneWire);
float last_temp = 25.0;
unsigned long last_temp_read = 0;

// Drum encoder state
volatile unsigned long last_pwm_rise = 0;
volatile unsigned long pwm_width = 0;
volatile bool pwm_updated = false;
int drum_position = 0;
int home_position = -1;
bool homing_done = false;

// Door state tracking
bool door_is_open = false;
bool motor_is_on = false;

void setRelay(int relay, bool on) {
  int pin = -1;
  if (relay == 1) pin = RELAY1;
  else if (relay == 2) pin = RELAY2;
  else if (relay == 3) pin = RELAY3;
  else if (relay == 4) pin = RELAY4;
  if (pin < 0) return;
  digitalWrite(pin, on ? RELAY_ON : RELAY_OFF);
}

void allRelaysOff() {
  for (int r = 1; r <= 4; r++) setRelay(r, false);
  motor_is_on = false;
}

void pulseRelay(int relay, int ms) {
  setRelay(relay, true);
  delay(ms);
  setRelay(relay, false);
}

// -- PWM interrupt for AS5045 --
void IRAM_ATTR pwm_isr() {
  static unsigned long last_time = 0;
  unsigned long now = micros();
  int val = digitalRead(DRUM_ENC);
  if (val == HIGH) {
    last_pwm_rise = now;
  } else {
    pwm_width = now - last_pwm_rise;
    pwm_updated = true;
  }
}

int readDrumPosition() {
  if (pwm_updated) {
    pwm_updated = false;
    // PWM width: ~1ms (0deg) to ~2ms (360deg) at 50Hz
    // Map to 0-360 degrees, then to slot position 0-5
    if (pwm_width > 500 && pwm_width < 2500) {
      int degrees = map(pwm_width, 1000, 2000, 0, 360);
      drum_position = constrain(degrees, 0, 359);
    }
  }
  return drum_position;
}

int readButton() {
  return digitalRead(BUTTON_PIN) == LOW ? 1 : 0;
}

float readTemperature() {
  if (millis() - last_temp_read > 2000) {
    sensors.requestTemperatures();
    float t = sensors.getTempCByIndex(0);
    if (t > -50 && t < 100) {
      last_temp = t;
    }
    last_temp_read = millis();
  }
  return last_temp;
}

void printStatus() {
  char buf[256];
  int pos = readDrumPosition();
  float temp = readTemperature();
  snprintf(buf, sizeof(buf),
    "OK DOOR=%s MOTOR=%s BUTTON=%s DRUM=%d HOME=%d TEMP=%.1f",
    door_is_open ? "OPEN" : "CLOSED",
    motor_is_on ? "ON" : "OFF",
    readButton() ? "ON" : "OFF",
    pos,
    home_position,
    temp
  );
  Serial.println(buf);
}

void cmdHome() {
  // Pulse motor while watching encoder for home position
  // If home_position is set, rotate until we reach it
  if (home_position < 0) {
    // No calibration - just pulse
    pulseRelay(4, PULSE_MS);
    Serial.println("OK");
    return;
  }
  // Try to reach home by short pulses
  for (int i = 0; i < 10; i++) {
    pulseRelay(4, 200);
    delay(50);
    int pos = readDrumPosition();
    if (abs(pos - home_position) < 10) {
      homing_done = true;
      Serial.println("OK");
      return;
    }
  }
  Serial.println("ERR HOMING_FAILED");
}

void cmdVendSlot(int slot) {
  // Each slot is ~60 degrees apart (6 slots)
  // Pulse motor to advance
  pulseRelay(4, PULSE_MS);
  motor_is_on = false;
  // Open door
  pulseRelay(1, PULSE_MS);
  door_is_open = true;
  delay(500);
  // Close door after vend
  pulseRelay(1, PULSE_MS);
  door_is_open = false;
  Serial.println("OK");
}

void cmdDoorOpen() {
  pulseRelay(1, PULSE_MS);
  door_is_open = true;
  Serial.println("OK");
}

void cmdDoorClose() {
  pulseRelay(1, PULSE_MS);
  door_is_open = false;
  Serial.println("OK");
}

void cmdMotorOn() {
  setRelay(4, true);
  motor_is_on = true;
  Serial.println("OK");
}

void cmdMotorOff() {
  setRelay(4, false);
  motor_is_on = false;
  Serial.println("OK");
}

void cmdPulse(int relay, int ms) {
  if (relay < 1 || relay > 4) {
    Serial.println("ERR UNKNOWN_CMD");
    return;
  }
  pulseRelay(relay, ms);
  Serial.println("OK");
}

void cmdRelay(int relay, bool on) {
  if (relay < 1 || relay > 4) {
    Serial.println("ERR UNKNOWN_CMD");
    return;
  }
  setRelay(relay, on);
  if (relay == 1) door_is_open = on;
  if (relay == 4) motor_is_on = on;
  Serial.println("OK");
}

void cmdEncCalibrate() {
  // Read current encoder position as home
  delay(10);
  home_position = readDrumPosition();
  homing_done = true;
  Serial.println("OK");
}

void handleCommand(String cmd) {
  cmd.trim();

  if (cmd == "DOOR_OPEN") { cmdDoorOpen(); return; }
  if (cmd == "DOOR_CLOSE") { cmdDoorClose(); return; }
  if (cmd == "MOTOR_ON") { cmdMotorOn(); return; }
  if (cmd == "MOTOR_OFF") { cmdMotorOff(); return; }
  if (cmd == "HOME") { cmdHome(); return; }
  if (cmd == "STATUS") { printStatus(); return; }
  if (cmd == "ENC_CALIBRATE") { cmdEncCalibrate(); return; }
  if (cmd == "ALL_OFF") { allRelaysOff(); Serial.println("OK"); return; }
  if (cmd == "INFO") { Serial.println("OK ESP32_VENDING FIRMWARE v2.0"); return; }
  if (cmd == "TEMP") {
    char buf[32];
    snprintf(buf, sizeof(buf), "OK TEMP=%.1f", readTemperature());
    Serial.println(buf);
    return;
  }
  if (cmd == "COOL_ON") { setRelay(2, true); Serial.println("OK"); return; }
  if (cmd == "COOL_OFF") { setRelay(2, false); Serial.println("OK"); return; }

  // VEND_SLOT N
  if (cmd.startsWith("VEND_SLOT ")) {
    int slot = cmd.substring(10).toInt();
    if (slot >= 1 && slot <= 6) { cmdVendSlot(slot); return; }
  }

  // RELAY N ON|OFF
  if (cmd.startsWith("RELAY ")) {
    int sp1 = cmd.indexOf(' ', 6);
    if (sp1 > 0) {
      int relay = cmd.substring(6, sp1).toInt();
      String action = cmd.substring(sp1 + 1);
      if (action == "ON") { cmdRelay(relay, true); return; }
      if (action == "OFF") { cmdRelay(relay, false); return; }
    }
  }

  // PINO N [ms] - pulse relay
  if (cmd.startsWith("PINO ")) {
    int sp1 = cmd.indexOf(' ', 5);
    if (sp1 > 0) {
      int relay = cmd.substring(5, sp1).toInt();
      int ms = cmd.substring(sp1 + 1).toInt();
      if (ms < 50) ms = PULSE_MS;
      cmdPulse(relay, ms);
      return;
    }
    int relay = cmd.substring(5).toInt();
    cmdPulse(relay, PULSE_MS);
    return;
  }

  Serial.println("ERR UNKNOWN_CMD");
}

void setup() {
  pinMode(RELAY1, OUTPUT);
  pinMode(RELAY2, OUTPUT);
  pinMode(RELAY3, OUTPUT);
  pinMode(RELAY4, OUTPUT);
  allRelaysOff();

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(DRUM_ENC, INPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);

  // PWM interrupt for AS5045
  attachInterrupt(digitalPinToInterrupt(DRUM_ENC), pwm_isr, CHANGE);

  // Temperature sensor
  sensors.begin();

  Serial.begin(SERIAL_BAUD);
  delay(500);
  Serial.println("ESP32_VENDING_READY");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    handleCommand(cmd);
  }
}
