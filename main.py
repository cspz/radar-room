"""
main.py
Entry point for the radar-room project.

When hardware arrives:
  1. Set USE_REAL_SENSOR = True
  2. Set SERIAL_PORT to your actual port (run: ls /dev/tty.usb* in terminal)
  3. Run: python main.py
"""

from sensor.simulator import Simulator

# ── THE SWITCH ────────────────────────────────────────────────────────────────

USE_REAL_SENSOR = False                       # flip to True when hardware arrives
SERIAL_PORT     = "/dev/tty.usbserial-0001"   # change to your actual port
BAUD_RATE       = 256000                       # LD2450 default baud rate
FPS             = 10.0                         # frames per second

# ── SCENE (only used in simulator mode) ──────────────────────────────────────

SCENE = "walking"    # options: empty / sitting / walking / two_people


# ── SOURCE FACTORY ────────────────────────────────────────────────────────────

def make_source():
    """Returns the active data source — real or simulated."""
    if USE_REAL_SENSOR:
        from sensor.ld2450 import LD2450
        print(f"[main] connecting to real sensor on {SERIAL_PORT}...")
        return LD2450(port=SERIAL_PORT, baud=BAUD_RATE)
    else:
        print(f"[main] using simulator  (scene: {SCENE})")
        return Simulator(scene=SCENE, fps=FPS)


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def main():
    source = make_source()
    from viz.dashboard import Dashboard
    print("[main] launching dashboard — close window to quit")
    db = Dashboard(source)
    db.run()


if __name__ == "__main__":
    main()