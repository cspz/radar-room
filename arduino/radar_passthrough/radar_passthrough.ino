// Passthrough — flash this for transparent UART bridge
#include <HardwareSerial.h>

HardwareSerial RadarSerial(2);

void setup() {
  Serial.begin(115200);
  Serial.println("radar_passthrough ready");
  RadarSerial.begin(256000, SERIAL_8N1, 16, 17);
}

void loop() {
  while (RadarSerial.available()) Serial.write(RadarSerial.read());
  while (Serial.available()) RadarSerial.write(Serial.read());
}