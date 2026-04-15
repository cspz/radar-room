import serial
import time

try:
    s = serial.Serial('/dev/tty.usbserial-0001', 256000, timeout=1)
    print("Port opened. Waiting for data...")
    while True:
        if s.in_waiting > 0:
            data = s.read(s.in_waiting)
            print(f"Received {len(data)} bytes: {data.hex()}")
        time.sleep(0.1)
except Exception as e:
    print(f"Error: {e}")