"""
main.py
Main for the radar-room project.

When hardware arrives:
  1. Set USE_REAL_SENSOR = True
  2. Set SERIAL_PORT to your actual port (run: ls /dev/cu.usb* in terminal)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensor.simulator import Simulator

if TYPE_CHECKING:
    # Only imported for type checking — LD2450 requires pyserial at runtime
    from sensor.ld2450 import LD2450

# ── THE SWITCH ────────────────────────────────────────────────────────────────

USE_REAL_SENSOR = True                        # change to True if hardware available
SERIAL_PORT     = "/dev/cu.usbserial-0001"
BAUD_RATE       = 256000                       # LD2450 baud rate (lowered for stability)
FPS             = 10.0                         # frames per second

# ── SCENE (only used in simulator mode) ──────────────────────────────────────

SCENE = "two_people"    # options: empty / sitting / walking / two_people


# ── SOURCE FACTORY ────────────────────────────────────────────────────────────

def make_source() -> Simulator | LD2450:
    """Returns the active data source — real or simulated."""
    if USE_REAL_SENSOR:
        import serial.tools.list_ports
        from sensor.ld2450 import LD2450

        available_ports = [p.device for p in serial.tools.list_ports.comports()]

        if SERIAL_PORT in available_ports:
            selected_port = SERIAL_PORT
        else:
            # Prefer common macOS USB-UART bridges used by ESP32 boards.
            preferred = [
                p.device
                for p in serial.tools.list_ports.comports()
                if (
                    "usbserial" in p.device.lower()
                    or "usbmodem" in p.device.lower()
                    or "cp210" in (p.description or "").lower()
                    or "ch340" in (p.description or "").lower()
                )
            ]

            if not preferred:
                raise RuntimeError(
                    "[main] no USB serial devices found.\n"
                    "  → connect ESP32/USB cable and re-run\n"
                    "  → check with: python3 -m serial.tools.list_ports -v"
                )

            selected_port = preferred[0]
            print(
                f"[main] configured port {SERIAL_PORT} not found; "
                f"using detected port {selected_port}"
            )

        print(f"[main] connecting to real sensor on {selected_port}...")
        return LD2450(port=selected_port, baud=BAUD_RATE)
    else:
        print(f"[main] using simulator  (scene: {SCENE})")
        return Simulator(scene=SCENE, fps=FPS)


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def main() -> None:
    source = make_source()
    from viz.dashboard import Dashboard
    print("[main] launching dashboard — close window to quit")
    db = Dashboard(source)
    db.run()


if __name__ == "__main__":
    main()