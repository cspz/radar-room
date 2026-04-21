#include <HardwareSerial.h>

HardwareSerial RadarSerial(2);

void setup() {
  Serial.begin(256000);
  RadarSerial.begin(256000, SERIAL_8N1, 16, 17);
}

void loop() {
  while (RadarSerial.available()) Serial.write(RadarSerial.read());
  while (Serial.available()) RadarSerial.write(Serial.read());
}