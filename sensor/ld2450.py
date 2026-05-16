"""
sensor/ld2450.py
Real LD2450 hardware parser.

Reads binary frames from the sensor over UART and outputs
the same Frame + Target objects as the simulator.

Protocol reference: HLK-LD2450 datasheet
  - Frame header:  AA FF 03 00  (4 bytes)
  - Frame footer:  55 CC        (2 bytes)
  - Frame length:  30 bytes total  (4 header + 3×8 target data + 2 footer)
  - Up to 3 targets per frame, each 8 bytes

Encoding note: x, y, and speed use sign-magnitude (not two's complement).
  High byte bit 7 = sign bit: 1 = positive, 0 = negative.
  Lower 15 bits = magnitude.
  X: positive = right of sensor. Y: positive = in front of sensor (0–6000 mm).
  Speed raw value × 10 = mm/s; dividing by 100 gives m/s.
"""

import serial
import serial.tools.list_ports
import struct
import time
from dataclasses import dataclass
from typing import Generator

from sensor.simulator import Target, Frame   # reuse same data structures


# ── Protocol constants ────────────────────────────────────────────────────────

FRAME_HEADER = bytes([0xAA, 0xFF, 0x03, 0x00])
FRAME_FOOTER = bytes([0x55, 0xCC])
FRAME_LENGTH = 30          # total bytes per frame: 4 header + 24 data + 2 footer
TARGET_COUNT = 3           # max targets per frame
TARGET_BYTES = 8           # bytes per target

# ── Smoothing ─────────────────────────────────────────────────────────────────

EMA_ALPHA = 0.35           # 0 = max smoothing, 1 = no smoothing


# ── Parser ────────────────────────────────────────────────────────────────────

class LD2450:
    """
    Reads live data from HLK-LD2450 radar sensor.
    Drop-in replacement for Simulator — same next_frame() and stream() interface.
    """

    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port  = port
        self.baud  = baud
        self._ser  = None
        self._rx_buf = bytearray()
        self._bytes_seen = 0
        # EMA state: dict of slot index → (x, y, speed)
        self._ema: dict[int, tuple[float, float, float]] = {}
        self._open()
        self._probe_stream()

    def _open(self) -> None:
        try:
            self._ser = serial.Serial(
                port      = self.port,
                baudrate  = self.baud,
                bytesize  = serial.EIGHTBITS,
                parity    = serial.PARITY_NONE,
                stopbits  = serial.STOPBITS_ONE,
                timeout   = 0.05,
                dsrdtr    = False,
                rtscts    = False,
            )
            print(f"[ld2450] opened {self.port} at {self.baud} baud")
        except serial.SerialException as e:
            raise RuntimeError(
                f"[ld2450] could not open {self.port}\n"
                f"  → {e}\n"
                f"  → run:  ls /dev/cu.usb*  to find your port"
            )

    def _flush_stale(self) -> None:
        """
        Discard buffered bytes that have piled up so we always parse
        the freshest frame. Keeps only the last 2 frames worth of data.
        """
        waiting = self._ser.in_waiting
        if waiting > FRAME_LENGTH * 4:
            # Read and discard everything except the last 2 frames
            discard = waiting - FRAME_LENGTH * 2
            dropped = self._ser.read(discard)
            self._bytes_seen += len(dropped)
            self._rx_buf.clear()

    def _read_frame_bytes(self) -> bytes | None:
        """
        Scans the serial stream for the next valid frame.
        Returns raw 28-byte frame or None on timeout.
        """
        self._flush_stale()

        deadline = time.time() + 0.5

        while time.time() < deadline:
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                self._rx_buf.extend(chunk)
                self._bytes_seen += len(chunk)

            # keep buffer bounded
            if len(self._rx_buf) > FRAME_LENGTH * 8:
                del self._rx_buf[:-FRAME_LENGTH * 4]

            while True:
                start = self._rx_buf.find(FRAME_HEADER)
                if start < 0:
                    keep = len(FRAME_HEADER) - 1
                    if len(self._rx_buf) > keep:
                        del self._rx_buf[:-keep]
                    break

                if start > 0:
                    del self._rx_buf[:start]

                if len(self._rx_buf) < FRAME_LENGTH:
                    break

                candidate = bytes(self._rx_buf[:FRAME_LENGTH])
                if candidate[-2:] == FRAME_FOOTER:
                    del self._rx_buf[:FRAME_LENGTH]
                    return candidate

                # Bad alignment: slide by one byte
                del self._rx_buf[0]

        return None

    def _probe_stream(self, timeout_s: float = 2.0) -> None:
        """
        Verify that valid LD2450 frames are actually present on this serial stream.
        Fails fast with actionable guidance instead of silently returning empty frames.
        """
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._read_frame_bytes() is not None:
                print("[ld2450] valid frames detected")
                return

        ports = [p.device for p in serial.tools.list_ports.comports()]
        details = "\n".join(f"  - {p}" for p in ports) if ports else "  (none)"
        self.close()
        raise RuntimeError(
            "[ld2450] connected but no valid LD2450 frames were detected.\n"
            f"  → port: {self.port}\n"
            f"  → baud: {self.baud}\n"
            f"  → bytes observed: {self._bytes_seen}\n"
            "  → likely causes:\n"
            "     1) ESP32 passthrough sketch not flashed/running\n"
            "     2) LD2450 TX/RX wiring mismatch on GPIO16/GPIO17\n"
            "     3) wrong baud between firmware and Python\n"
            "  → available serial ports:\n"
            f"{details}"
        )

    @staticmethod
    def _parse_target(data: bytes, offset: int) -> Target | None:
        """
        Parses one 8-byte target block starting at offset.
        Returns None if the slot is empty (all zeros).
        """
        raw_x, raw_y, raw_v, _ = struct.unpack_from('<HHHH', data, offset)

        def _sm(v: int) -> int:
            """Sign-magnitude decode: high-byte bit 7 = sign (1=positive, 0=negative)."""
            return (1 if v & 0x8000 else -1) * (v & 0x7FFF)

        x_mm  = _sm(raw_x)
        y_mm  = _sm(raw_y)
        v_cms = _sm(raw_v)

        if x_mm == 0 and y_mm == 0:
            return None

        if abs(x_mm) > 9000 or abs(y_mm) > 9000:
            return None

        return Target(
            x     = round(x_mm  / 1000.0, 3),
            y     = round(y_mm  / 1000.0, 3),
            speed = round(v_cms / 100.0,  3)
        )

    def _smooth(self, slot: int, t: Target) -> Target:
        """Apply exponential moving average to a target's coordinates."""
        if slot not in self._ema:
            self._ema[slot] = (t.x, t.y, t.speed)
            return t

        ex, ey, ev = self._ema[slot]
        sx = EMA_ALPHA * t.x     + (1 - EMA_ALPHA) * ex
        sy = EMA_ALPHA * t.y     + (1 - EMA_ALPHA) * ey
        sv = EMA_ALPHA * t.speed + (1 - EMA_ALPHA) * ev
        self._ema[slot] = (sx, sy, sv)

        return Target(
            x     = round(sx, 3),
            y     = round(sy, 3),
            speed = round(sv, 3)
        )

    def next_frame(self) -> Frame:
        """
        Blocks until one valid frame is received.
        Returns a Frame with 0-3 Target objects, EMA-smoothed.
        """
        while True:
            raw = self._read_frame_bytes()
            if raw is None:
                return Frame(targets=[], timestamp=time.time())

            targets = []
            active_slots = set()

            for i in range(TARGET_COUNT):
                offset = 4 + i * TARGET_BYTES
                t = self._parse_target(raw, offset)
                if t is not None:
                    targets.append(self._smooth(i, t))
                    active_slots.add(i)

            # Clear EMA state for slots that went inactive
            for slot in list(self._ema.keys()):
                if slot not in active_slots:
                    del self._ema[slot]

            return Frame(targets=targets, timestamp=time.time())

    def stream(self) -> Generator[Frame, None, None]:
        """Generator — yields frames continuously. Same interface as Simulator."""
        while True:
            yield self.next_frame()

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            print(f"[ld2450] closed {self.port}")

    def __del__(self) -> None:
        self.close()