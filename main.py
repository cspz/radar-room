"""
main.py
Main for the radar-room project.

When hardware arrives:
  1. Set USE_REAL_SENSOR = True
  2. Set SERIAL_PORT to your actual port (run: ls /dev/tty.usb* in terminal)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensor.simulator import Simulator

if TYPE_CHECKING:
    # Only imported for type checking — LD2450 requires pyserial at runtime
    from sensor.ld2450 import LD2450

# ── THE SWITCH ────────────────────────────────────────────────────────────────

USE_REAL_SENSOR = False                        # change to True if hardware available
SERIAL_PORT     = "/dev/tty.usbserial-0001"    # change to actual port
BAUD_RATE       = 256000                       # LD2450 default baud rate
FPS             = 10.0                         # frames per second

# ── SCENE (only used in simulator mode) ──────────────────────────────────────

SCENE = "two_people"    # options: empty / sitting / walking / two_people


# ── SOURCE FACTORY ────────────────────────────────────────────────────────────

def make_source() -> Simulator | LD2450:
    """Returns the active data source — real or simulated."""
    if USE_REAL_SENSOR:
        from sensor.ld2450 import LD2450
        print(f"[main] connecting to real sensor on {SERIAL_PORT}...")
        return LD2450(port=SERIAL_PORT, baud=BAUD_RATE)
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