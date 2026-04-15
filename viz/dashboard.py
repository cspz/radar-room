"""
viz/dashboard.py
Real-time bird's-eye radar visualization.
Always run via main.py
"""

import sys
import threading
import queue
import math
from typing import Any

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

# add project root to path
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__file__)))


# ── Config ────────────────────────────────────────────────────────────────────

FPS           = 10
ROOM_W        = 6.0    # meters, left-right
ROOM_D        = 8.0    # meters, depth
TRAIL_LEN     = 30     # past positions to show per target
TRAIL_ALPHA_MIN = 25   # oldest trail point alpha
TRAIL_ALPHA_MAX = 150  # newest trail point alpha
EMA_ALPHA     = 0.35   # lower = smoother but more lag
TRACK_MAX_DIST = 1.2   # meters; slot assignment gate between frames
MISS_GRACE_FRAMES = 3  # keep last known point this many missed updates

TARGET_COLORS = [
    (50,  205,  50, 255),   # green — target 1
    (30,  144, 255, 255),   # blue  — target 2
    (255,  80,  80, 255),   # red   — target 3
]


# ── Dashboard class ───────────────────────────────────────────────────────────

class Dashboard:

    def __init__(self, source: Any) -> None:
        """
        source: anything with a next_frame() method
                (Simulator or LD2450 - doesn't matter)
        """
        self.source  = source
        # One history buffer per target slot (max 3 targets from LD2450)
        self.history: list[list[tuple[float, float]]] = [[] for _ in range(3)]
        # Per-slot smoothed position state for EMA filtering
        self.smoothed: list[tuple[float, float] | None] = [None, None, None]
        self.missed_frames: list[int] = [0, 0, 0]

        # Frame queue: background thread pushes, UI thread pops (non-blocking)
        self.frame_queue: queue.Queue = queue.Queue(maxsize=2)
        self._stop_event = threading.Event()

        # Qt app + window
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.win = pg.GraphicsLayoutWidget(title="radar-room — live view")
        self.win.resize(700, 820)
        self.win.setBackground('#111111')

        # plot area
        self.plot = self.win.addPlot(title="")
        self._setup_plot()

        # Two scatter layers per target: semi-transparent trail dots + solid current dot
        self.trail_items:  list[pg.ScatterPlotItem] = []
        self.target_items: list[pg.ScatterPlotItem] = []
        for color in TARGET_COLORS:
            trail = pg.ScatterPlotItem(size=6, pen=None)
            dot   = pg.ScatterPlotItem(size=16, pen=pg.mkPen('w', width=1),
                                       brush=pg.mkBrush(*color))
            self.plot.addItem(trail)
            self.plot.addItem(dot)
            self.trail_items.append(trail)
            self.target_items.append(dot)

        # status bar
        self.label = pg.LabelItem(justify='left')
        self.win.addItem(self.label, row=1, col=0)

        # Start background frame reader thread
        self._reader_thread = threading.Thread(target=self._frame_reader_loop, daemon=True)
        self._reader_thread.start()

        # timer drives UI updates (non-blocking)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(int(1000 / FPS))

    def _frame_reader_loop(self) -> None:
        """
        Background thread: continuously reads frames from the sensor
        and pushes them to the frame queue for the UI thread.
        """
        print("[dashboard] frame reader thread started")
        while not self._stop_event.is_set():
            try:
                frame = self.source.next_frame()
                # Drop oldest frame if queue is full (keep latest data flowing)
                try:
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self.frame_queue.put_nowait(frame)
            except Exception as e:
                print(f"[dashboard] frame reader ERROR: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                self._stop_event.set()

    def _setup_plot(self) -> None:
        p = self.plot
        p.setAspectLocked(True)
        p.setXRange(-ROOM_W / 2, ROOM_W / 2, padding=0.05)
        p.setYRange(0, ROOM_D, padding=0.05)
        p.setLabel('bottom', 'x  (meters)')
        p.setLabel('left',   'y  (meters — distance from sensor)')

        # sensor marker at origin
        p.addItem(pg.ScatterPlotItem(
            pos=[(0, 0)], size=14,
            pen=pg.mkPen('#ffffff', width=2),
            brush=pg.mkBrush('#ffffff'),
            symbol='t1'
        ))

        # field-of-view cone ±60°
        angles = np.linspace(np.radians(-60), np.radians(60), 60)
        fov_x  = np.concatenate([[0], ROOM_D * np.sin(angles), [0]])
        fov_y  = np.concatenate([[0], ROOM_D * np.cos(angles), [0]])
        p.addItem(pg.PlotDataItem(fov_x, fov_y,
                                  pen=pg.mkPen('#334455', width=1),
                                  fillLevel=0,
                                  brush=pg.mkBrush(30, 80, 120, 25)))

        # range rings
        for r in [2, 4, 6, 8]:
            theta = np.linspace(np.radians(-70), np.radians(70), 80)
            p.addItem(pg.PlotDataItem(r * np.sin(theta), r * np.cos(theta),
                                      pen=pg.mkPen('#223344', width=0.8)))
            lbl = pg.TextItem(f'{r}m', color='#445566', anchor=(0.5, 1))
            lbl.setPos(0, r)
            p.addItem(lbl)

    def _update(self) -> None:
        """
        UI timer callback (non-blocking). Drains queue and renders only newest frame.
        Runs on the main Qt thread.
        """
        frame = None
        while True:
            try:
                # Keep only the most recent frame to minimize visual latency.
                frame = self.frame_queue.get_nowait()
            except queue.Empty:
                break

        if frame is None:
            # No new frame yet — skip update, use last known state
            return

        n     = len(frame.targets)
        assigned = self._assign_targets_to_slots(frame.targets)
        display_positions: list[tuple[float, float, float]] = []

        for slot in range(3):
            t = assigned[slot]
            if t is not None:
                prev = self.smoothed[slot]
                if prev is None:
                    sx, sy = t.x, t.y
                else:
                    sx = EMA_ALPHA * t.x + (1.0 - EMA_ALPHA) * prev[0]
                    sy = EMA_ALPHA * t.y + (1.0 - EMA_ALPHA) * prev[1]
                self.smoothed[slot] = (sx, sy)
                self.missed_frames[slot] = 0

                # Append current position to the rolling trail buffer
                self.history[slot].append((sx, sy))
                if len(self.history[slot]) > TRAIL_LEN:
                    self.history[slot].pop(0)
                # Draw trail from all but the most-recent point (which gets the big dot)
                hx = [p[0] for p in self.history[slot][:-1]]
                hy = [p[1] for p in self.history[slot][:-1]]
                if hx:
                    base = TARGET_COLORS[slot][:3]
                    # Oldest points are fainter; most recent trail points are brighter.
                    alphas = np.linspace(TRAIL_ALPHA_MIN, TRAIL_ALPHA_MAX, len(hx), dtype=int)
                    brushes = [pg.mkBrush(base[0], base[1], base[2], int(a)) for a in alphas]
                    self.trail_items[slot].setData(hx, hy, brush=brushes)
                else:
                    self.trail_items[slot].setData([], [])
                self.target_items[slot].setData([sx], [sy])
                display_positions.append((sx, sy, t.speed))
            else:
                # Briefly hold last position to mask one-off sensor misses.
                self.missed_frames[slot] += 1
                if self.smoothed[slot] is not None and self.missed_frames[slot] <= MISS_GRACE_FRAMES:
                    sx, sy = self.smoothed[slot]
                    self.target_items[slot].setData([sx], [sy])
                else:
                    # Target slot is truly empty — clear visuals and state
                    self.trail_items[slot].setData([], [])
                    self.target_items[slot].setData([], [])
                    self.history[slot].clear()
                    self.smoothed[slot] = None
                    self.missed_frames[slot] = 0

        # Show scene name when using the simulator; fall back to 'live' for real hardware
        scene_str = getattr(self.source, 'scene', 'live').replace('_', ' ')
        if n == 0:
            status = f"<span style='color:#888'>scene: {scene_str} &nbsp;|&nbsp; no targets</span>"
        else:
            colors = ['#32cd32', '#1e90ff', '#ff5050']
            parts  = [
                f"<span style='color:{colors[i]}'>"
                f"T{i+1}: ({pos[0]:+.2f}, {pos[1]:.2f})m &nbsp;{pos[2]:+.2f}m/s</span>"
                for i, pos in enumerate(display_positions)
            ]
            status = f"<span style='color:#888'>scene: {scene_str} &nbsp;|&nbsp; </span>" + \
                     " &nbsp; ".join(parts)
        self.label.setText(status)

    def _assign_targets_to_slots(self, targets: list[Any]) -> list[Any | None]:
        """
        Keeps slot identity stable frame-to-frame by assigning detections to
        prior smoothed positions using nearest-neighbor matching.
        """
        assigned: list[Any | None] = [None, None, None]
        used_targets: set[int] = set()

        # Prefer continuity for slots that already have a previous position.
        candidates: list[tuple[float, int, int]] = []
        for slot in range(3):
            prev = self.smoothed[slot]
            if prev is None:
                continue
            for idx, t in enumerate(targets):
                d = math.hypot(t.x - prev[0], t.y - prev[1])
                candidates.append((d, slot, idx))

        for d, slot, idx in sorted(candidates, key=lambda x: x[0]):
            if d > TRACK_MAX_DIST:
                continue
            if assigned[slot] is not None or idx in used_targets:
                continue
            assigned[slot] = targets[idx]
            used_targets.add(idx)

        # Fill empty slots with any remaining targets.
        leftovers = [targets[i] for i in range(len(targets)) if i not in used_targets]
        li = 0
        for slot in range(3):
            if assigned[slot] is None and li < len(leftovers):
                assigned[slot] = leftovers[li]
                li += 1

        return assigned

    def run(self) -> None:
        """
        Starts the Qt event loop. Stops the background thread when the window closes.
        """
        self.win.show()
        try:
            sys.exit(self.app.exec())
        finally:
            self._stop_event.set()
            self._reader_thread.join(timeout=2.0)