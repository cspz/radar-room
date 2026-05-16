"""Single-command sensor diagnostics: stream verdict + parser test."""

from __future__ import annotations


import traceback
from collections import Counter

import serial.tools.list_ports


SERIAL_PORT = "/dev/cu.usbserial-0001"
BAUD_RATE = 115200
SAMPLE_SECONDS = 2.0


def _run_stream_probe(port: str, baud: int, seconds: float) -> tuple[bool, str]:
    """Return (has_valid_frames, report_text) for a short raw-stream probe."""
    from probe_serial import capture, count_frames, SIGNATURES

    data = capture(port, baud, seconds)
    if not data:
        return False, "[stream] no bytes received"

    ctr = Counter(data)
    zero_ratio = (ctr.get(0, 0) / len(data)) * 100.0
    top = ", ".join(f"0x{b:02X}({n})" for b, n in ctr.most_common(5))

    lines = [
        f"[stream] captured {len(data)} bytes in {seconds:.1f}s",
        f"[stream] zero-byte ratio: {zero_ratio:.1f}%",
        f"[stream] top bytes: {top}",
        "[stream] signature scan:",
    ]

    any_valid = False
    for name, header, footer, length in SIGNATURES:
        header_hits, valid = count_frames(data, header, footer, length)
        lines.append(f"  - {name}: headerHits={header_hits}, validFrames={valid}")
        if valid > 0:
            any_valid = True

    verdict = "GREEN" if any_valid else "RED"
    lines.append(f"[stream] verdict: {verdict}")

    if not any_valid:
        lines.append("[stream] likely physical link issue: firmware, wiring, or pin mapping")

    return any_valid, "\n".join(lines)


def main() -> int:
    print(f"Attempting to connect to {SERIAL_PORT} at {BAUD_RATE} baud...")

    ports = [p.device for p in serial.tools.list_ports.comports()]
    if SERIAL_PORT not in ports:
        print(f"\n[precheck] selected port not found: {SERIAL_PORT}")
        print("[precheck] available ports:")
        for p in ports:
            print(f"  - {p}")
        return 2

    ok, report = _run_stream_probe(SERIAL_PORT, BAUD_RATE, SAMPLE_SECONDS)
    print("\n" + report)

    if not ok:
        print("\nStop here and fix hardware path before parser test.")
        return 1

    try:
        from sensor.ld2450 import LD2450

        sensor = LD2450(port=SERIAL_PORT, baud=BAUD_RATE)
        print("\n[parser] sensor connected and valid stream confirmed")

        print("\nReading 5 frames...")
        for i in range(5):
            print(f"\nFrame {i + 1}:")
            frame = sensor.next_frame()
            print(f"  Timestamp: {frame.timestamp}")
            print(f"  Targets: {len(frame.targets)}")
            for j, target in enumerate(frame.targets):
                print(
                    f"    T{j + 1}: x={target.x:.2f}m, "
                    f"y={target.y:.2f}m, speed={target.speed:.2f}m/s"
                )

        sensor.close()
        print("\n[parser] sensor test completed successfully")
        return 0

    except Exception as e:
        print(f"\n[parser] error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
