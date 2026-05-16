"""
Loopback test for ESP32 passthrough sketch.

Before running:
  1. Disconnect LD2450 from ESP32
  2. Bridge GPIO16 → GPIO17 with a jumper wire (or a piece of wire)
  3. Run: python3 loopback_test.py

PASS = sketch is running, USB path works, LD2450 wiring/power is the problem
FAIL = sketch is not running or USB path is broken → reflash ESP32
"""

import sys
import time
import serial
import serial.tools.list_ports

PORT = "/dev/cu.usbserial-0001"
BAUD = 115200
PAYLOAD = b"\xAA\xFF\x03\x00\xDE\xAD\xBE\xEF\x55\xCC"


def main() -> int:
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if PORT not in ports:
        print(f"Port not found: {PORT}")
        print("Available:", ports)
        return 2

    print(f"Opening {PORT} @ {BAUD}...")
    with serial.Serial(PORT, BAUD, timeout=1.0, dsrdtr=False, rtscts=False) as ser:
        ser.reset_input_buffer()
        time.sleep(0.1)

        print(f"Sending {len(PAYLOAD)} bytes: {PAYLOAD.hex()}")
        ser.write(PAYLOAD)
        ser.flush()

        time.sleep(0.2)
        echo = ser.read(len(PAYLOAD))

    if echo == PAYLOAD:
        print(f"\nPASS — received back: {echo.hex()}")
        print("Sketch is running. Problem is in LD2450 wiring or power.")
        return 0

    if echo:
        print(f"\nPARTIAL — sent {len(PAYLOAD)}B, got back {len(echo)}B: {echo.hex()}")
        print("Possible baud mismatch or sketch partially running.")
    else:
        print("\nFAIL — no echo received")
        print("Sketch is not running. Reflash the ESP32.")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
