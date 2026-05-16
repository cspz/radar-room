"""
Probe raw serial data and report whether known radar frame signatures are present.

Usage:
  python3 probe_serial.py
  python3 probe_serial.py /dev/cu.usbserial-0001 256000 2.5
"""

from __future__ import annotations

import sys
import time
from collections import Counter

import serial
import serial.tools.list_ports


DEFAULT_PORT = "/dev/cu.usbserial-0001"
DEFAULT_BAUD = 115200
DEFAULT_SECONDS = 2.0

# Common mmWave frame signatures used by HLK modules.
SIGNATURES = [
    ("LD2450_AAFF0300_55CC_30B", bytes([0xAA, 0xFF, 0x03, 0x00]), bytes([0x55, 0xCC]), 30),
    ("HLK_FDFCFBFA_04030201", bytes([0xFD, 0xFC, 0xFB, 0xFA]), bytes([0x04, 0x03, 0x02, 0x01]), None),
    ("HLK_F4F3F2F1_F8F7F6F5", bytes([0xF4, 0xF3, 0xF2, 0xF1]), bytes([0xF8, 0xF7, 0xF6, 0xF5]), None),
]


def capture(port: str, baud: int, seconds: float) -> bytes:
    with serial.Serial(port, baud, timeout=0.2, dsrdtr=False, rtscts=False) as ser:
        data = bytearray()
        deadline = time.time() + seconds
        while time.time() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                data.extend(chunk)
            time.sleep(0.01)
        return bytes(data)


def count_frames(data: bytes, header: bytes, footer: bytes, length: int | None) -> tuple[int, int]:
    header_hits = data.count(header)
    valid = 0
    i = 0
    while True:
        j = data.find(header, i)
        if j < 0:
            break
        if length is not None:
            end = j + length
            if end <= len(data) and data[end - len(footer):end] == footer:
                valid += 1
        else:
            k = data.find(footer, j + len(header))
            if k >= 0:
                valid += 1
        i = j + 1
    return header_hits, valid


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BAUD
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_SECONDS

    ports = [p.device for p in serial.tools.list_ports.comports()]
    print("Available serial ports:")
    for p in ports:
        print(f"  - {p}")

    if port not in ports:
        print(f"\nSelected port not present: {port}")
        return 2

    print(f"\nCapturing {seconds:.1f}s from {port} @ {baud}...")
    data = capture(port, baud, seconds)
    print(f"Captured bytes: {len(data)}")

    if not data:
        print("No data received.")
        return 1

    ctr = Counter(data)
    most_common = ctr.most_common(8)
    printable = sum(1 for b in data if 32 <= b <= 126)
    zero_ratio = (ctr.get(0, 0) / len(data)) * 100.0
    printable_ratio = (printable / len(data)) * 100.0

    print("\nByte profile:")
    print(f"  zero-byte ratio: {zero_ratio:.1f}%")
    print(f"  printable ratio: {printable_ratio:.1f}%")
    print("  top bytes:", ", ".join(f"0x{b:02X}({n})" for b, n in most_common))

    print("\nSignature scan:")
    any_valid = False
    for name, header, footer, length in SIGNATURES:
        header_hits, valid = count_frames(data, header, footer, length)
        if valid > 0:
            any_valid = True
        print(f"  {name}: headerHits={header_hits}, validFrames={valid}")

    if any_valid:
        print("\nResult: Valid radar-like frames were found.")
        return 0

    print("\nResult: No known frame signatures detected.")
    print("Likely causes: passthrough firmware, wiring, or baud mismatch.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
