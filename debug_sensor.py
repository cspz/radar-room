"""
Debug script to test sensor connection
"""

import sys
import time

SERIAL_PORT = "/dev/cu.usbserial-0001"
BAUD_RATE = 256000

print(f"Attempting to connect to {SERIAL_PORT} at {BAUD_RATE} baud...")

try:
    from sensor.ld2450 import LD2450
    
    sensor = LD2450(port=SERIAL_PORT, baud=BAUD_RATE)
    print("✓ Sensor connected!")
    
    print("\nReading 5 frames...")
    for i in range(5):
        print(f"\nFrame {i+1}:")
        frame = sensor.next_frame()
        print(f"  Timestamp: {frame.timestamp}")
        print(f"  Targets: {len(frame.targets)}")
        for j, target in enumerate(frame.targets):
            print(f"    T{j+1}: x={target.x:.2f}m, y={target.y:.2f}m, speed={target.speed:.2f}m/s")
    
    sensor.close()
    print("\n✓ Sensor test completed successfully")
    
except Exception as e:
    print(f"\n✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
