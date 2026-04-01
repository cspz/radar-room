# Radar Room

> **Note:** Waiting for hardware — only simulation tested so far (30 March 2026).


Real-time human presence detection and activity classification using a 24GHz FMCW radar sensor.

A single HLK-LD2450 radar module streams target position and velocity data over UART to a Mac. A Python pipeline parses the binary frames and visualizes them live in a bird's-eye dashboard, all for under EUR 20 of hardware. An ML activity classifier is planned.

---

## Demo

> live demo GIF goes here once hardware arrives

---

## How it works

The HLK-LD2450 is a 24GHz FMCW (Frequency Modulated Continuous Wave) radar sensor. It continuously broadcasts radio chirps that bounce off people in the room. By analyzing the reflected signals it computes the X/Y position and radial speed of up to 3 targets simultaneously, and streams this as binary frames over UART at 10Hz.

The Python pipeline:

1. Reads and parses binary frames from the sensor via USB serial
2. Converts raw millimetre values to metres
3. Renders a live bird's-eye visualization with target trails
4. Classifies the current room activity using a trained scikit-learn model

No camera. No cloud. Everything runs locally.

---

## Hardware

| Component | Details | Price |
| --- | --- | --- |
| HLK-LD2450 | 24GHz FMCW radar, ±60° FOV, 8m range | ~€11 |
| ESP32 WROOM-32D | CP2102 USB-UART bridge, USB-C | ~€5 |
| Jumper wires | Female-female, 20cm | ~€2 |
| **Total** | | **~€18** |

### Wiring

```text
LD2450        ESP32
──────────────────────
VCC (red)  →  VIN
GND (blk)  →  GND
TX  (grn)  →  GPIO16
RX  (yel)  →  GPIO17
```

ESP32 connects to Mac via USB-C. No soldering required.

---

## Project structure

```text
radar-room/
├── sensor/
│   ├── simulator.py   # realistic fake data for development without hardware
│   └── ld2450.py      # real UART parser for HLK-LD2450
├── viz/
│   └── dashboard.py   # live bird's-eye PyQtGraph visualization
├── ml/
│   ├── collect.py     # record labelled sessions for training
│   ├── train.py       # train scikit-learn activity classifier
│   └── inference.py   # run live ML predictions on radar stream
├── main.py            # entry point — one switch for real vs simulated data
├── requirements.txt
└── README.md
```

---

## Quickstart

### 1. Clone and set up environment

```bash
git clone https://github.com/cspz/radar-room.git
cd radar-room
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run with simulated data (no hardware needed)

```bash
python3 main.py
```

A live dashboard opens immediately. Change the scene at the top of `main.py`:

```python
SCENE = "walking"    # empty / sitting / walking / two_people
```

### 3. Run with real hardware

Connect the LD2450 via ESP32 and USB-C. Find your serial port:

```bash
ls /dev/tty.usb*
```

Then in `main.py` set:

```python
USE_REAL_SENSOR = True
SERIAL_PORT     = "/dev/tty.usbserial-XXXX"   # your actual port
```

Run:

```bash
python3 main.py
```

---

## Dashboard

The visualization shows:

- **White triangle** — sensor position at origin
- **Blue cone** — 60° field of view
- **Range rings** — at 2m, 4m, 6m, 8m
- **Coloured dots** — live target positions (green / blue / red for targets 1-2-3)
- **Trails** — last 30 positions per target
- **Status bar** — real-time coordinates and speed per target

---

## ML activity classifier

Record labelled sessions, train a classifier, run live inference:

```bash
# record data
python3 ml/collect.py --label walking --duration 60

# train model
python3 ml/train.py

# run with live inference
python3 main.py --ml
```

Supported activity classes: `empty` · `sitting` · `walking` · `two_people`

> Planned — not yet implemented.

---

## Dependencies

```text
pyserial
numpy
pyqtgraph
PyQt6
scikit-learn
```

Install all:

```bash
pip install -r requirements.txt
```

---

## Roadmap

- [x] Simulator with realistic physics-based scenes
- [x] Binary UART parser for HLK-LD2450
- [x] Real-time bird's-eye dashboard
- [ ] ML activity classifier
- [ ] Live inference overlay on dashboard
- [ ] Multi-sensor triangulation (3x LD2450)
- [ ] 3D visualization


---

## License

MIT
