"""
viz/dashboard.py
Real-time bird's-eye radar visualization.
Always run via main.py
"""

import sys
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
TRAIL_ALPHA   = 60     # transparency of trail dots

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
            trail = pg.ScatterPlotItem(size=6,  pen=None,
                                       brush=pg.mkBrush(*color[:3], TRAIL_ALPHA))
            dot   = pg.ScatterPlotItem(size=16, pen=pg.mkPen('w', width=1),
                                       brush=pg.mkBrush(*color))
            self.plot.addItem(trail)
            self.plot.addItem(dot)
            self.trail_items.append(trail)
            self.target_items.append(dot)

        # status bar
        self.label = pg.LabelItem(justify='left')
        self.win.addItem(self.label, row=1, col=0)

        # timer drives updates
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(int(1000 / FPS))

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
        frame = self.source.next_frame()
        n     = len(frame.targets)

        for slot in range(3):
            if slot < n:
                t = frame.targets[slot]
                # Append current position to the rolling trail buffer
                self.history[slot].append((t.x, t.y))
                if len(self.history[slot]) > TRAIL_LEN:
                    self.history[slot].pop(0)
                # Draw trail from all but the most-recent point (which gets the big dot)
                hx = [p[0] for p in self.history[slot][:-1]]
                hy = [p[1] for p in self.history[slot][:-1]]
                self.trail_items[slot].setData(hx, hy)
                self.target_items[slot].setData([t.x], [t.y])
            else:
                # Target slot is empty — clear its visuals and history
                self.trail_items[slot].setData([], [])
                self.target_items[slot].setData([], [])
                self.history[slot].clear()

        # Show scene name when using the simulator; fall back to 'live' for real hardware
        scene_str = getattr(self.source, 'scene', 'live').replace('_', ' ')
        if n == 0:
            status = f"<span style='color:#888'>scene: {scene_str} &nbsp;|&nbsp; no targets</span>"
        else:
            colors = ['#32cd32', '#1e90ff', '#ff5050']
            parts  = [
                f"<span style='color:{colors[i]}'>"
                f"T{i+1}: ({t.x:+.2f}, {t.y:.2f})m &nbsp;{t.speed:+.2f}m/s</span>"
                for i, t in enumerate(frame.targets)
            ]
            status = f"<span style='color:#888'>scene: {scene_str} &nbsp;|&nbsp; </span>" + \
                     " &nbsp; ".join(parts)
        self.label.setText(status)

    def run(self) -> None:
        self.win.show()
        sys.exit(self.app.exec())