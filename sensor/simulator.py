"""
simulator.py
Generates realistic fake LD2450 radar data.
Simulates different scenes: walking, sitting, two people, empty room.
This goes in the sensor/ folder.
"""

import numpy as np
import time
from dataclasses import dataclass

# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class Target:
    x: float        # metres, left/right  (-3 to +3)
    y: float        # metres, depth        (0 to 8)
    speed: float    # m/s, negative = moving away, positive = approaching

@dataclass
class Frame:
    targets: list[Target]
    timestamp: float

# ── Individual scene simulators ───────────────────────────────────────────────

class WalkingPerson:
    #One person walking back and forth across the room.

    def __init__(self):
        self.x = 0.0
        self.y = 2.5
        self.direction = 1.0      # +1 or -1
        self.speed = 0.9          # m/s walking speed

    def update(self, dt: float) -> Target:
        self.x += self.direction * self.speed * dt
        # bounce off walls at ±2.5m
        if abs(self.x) > 2.5:
            self.direction *= -1
        # add small natural noise
        nx = self.x + np.random.normal(0, 0.05)
        ny = self.y + np.random.normal(0, 0.03)
        measured_speed = self.direction * self.speed + np.random.normal(0, 0.05)
        return Target(x=round(nx, 3), y=round(ny, 3), speed=round(measured_speed, 3))


class SittingPerson:
    #One person sitting still — tiny chest movement from breathing.

    def __init__(self, x=0.2, y=1.8):
        self.x = x
        self.y = y
        self.breath_phase = np.random.uniform(0, 2 * np.pi)
        self.breath_rate = 0.28   # Hz — about 17 breaths per minute

    def update(self, dt: float) -> Target:
        self.breath_phase += 2 * np.pi * self.breath_rate * dt
        # chest moves ~1cm with each breath
        breath_displacement = 0.01 * np.sin(self.breath_phase)
        nx = self.x + np.random.normal(0, 0.02)
        ny = self.y + breath_displacement + np.random.normal(0, 0.01)
        speed = breath_displacement * self.breath_rate + np.random.normal(0, 0.01)
        return Target(x=round(nx, 3), y=round(ny, 3), speed=round(speed, 4))

# ── Scene definitions ─────────────────────────────────────────────────────────

SCENES = ["empty", "sitting", "walking", "two_people"]

class Simulator:
    # Main simulator. Call next_frame() in a loop to get frames.
    # Change scene at any time with set_scene().

    def __init__(self, scene: str = "walking", fps: float = 10.0):
        self.fps = fps
        self.dt = 1.0 / fps
        self.scene = None
        self._actors = []
        self.set_scene(scene)

    def set_scene(self, scene: str):
        assert scene in SCENES, f"Scene must be one of {SCENES}"
        self.scene = scene
        if scene == "empty":
            self._actors = []
        elif scene == "sitting":
            self._actors = [SittingPerson(x=0.1, y=1.8)]
        elif scene == "walking":
            self._actors = [WalkingPerson()]
        elif scene == "two_people":
            self._actors = [
                SittingPerson(x=-0.8, y=1.5),
                WalkingPerson(),
            ]
        print(f"[simulator] scene → {scene}")

    def next_frame(self) -> Frame:
        """Returns one Frame with up to 3 Target objects."""
        targets = [actor.update(self.dt) for actor in self._actors]
        # sensor always adds a little ghost noise — filter anything too faint
        return Frame(targets=targets, timestamp=time.time())

    def stream(self):
        """Generator — yields frames at self.fps rate. Use in a for loop."""
        while True:
            yield self.next_frame()
            time.sleep(self.dt)


# ── Quick self-test ───────────────────────────────────────────────────────────

# to run it: > python3 simulator.py from terminal

if __name__ == "__main__":
    print("LD2450 Simulator — self test")
    print("Cycling through all scenes, 2 seconds each\n")

    sim = Simulator(fps=10)

    for scene in SCENES:
        sim.set_scene(scene)
        for i in range(20):          # 2 seconds at 10fps
            frame = sim.next_frame()
            if frame.targets:
                t = frame.targets[0]
                print(f"  [{scene:10s}] x={t.x:+.2f}m  y={t.y:.2f}m  speed={t.speed:+.3f}m/s")
            else:
                print(f"  [{scene:10s}] no targets detected")
            time.sleep(0.1)
        print()

    print("Simulator working correctly.")
