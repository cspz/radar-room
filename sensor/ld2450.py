"""
sensor/ld2450.py
Real LD2450 hardware parser.

Reads binary frames from the sensor over UART and outputs
the same Frame + Target objects as the simulator.

Protocol reference: HLK-LD2450 datasheet
  - Frame header:  AA FF 03 00  (4 bytes)
  - Frame footer:  55 CC        (2 bytes)
  - Frame length:  28 bytes total
  - Up to 3 targets per frame, each 8 bytes

Encoding note: x, y, and speed use sign-magnitude (not two's complement).
  MSB = sign bit, lower 15 bits = magnitude.
  Y is reported negative for targets in front of the sensor.
  Speed is the Doppler radial velocity in cm/s, computed internally by the sensor.
"""

import serial
import struct
import time
from dataclasses import dataclass
from typing import Generator

from sensor.simulator import Target, Frame   # reuse same data structures


# ── Protocol constants ────────────────────────────────────────────────────────

FRAME_HEADER = bytes([0xAA, 0xFF, 0x03, 0x00])
FRAME_FOOTER = bytes([0x55, 0xCC])
FRAME_LENGTH = 28          # total bytes per frame
TARGET_COUNT = 3           # max targets per frame
TARGET_BYTES = 8           # bytes per target


# ── Parser ────────────────────────────────────────────────────────────────────

class LD2450:
    """
    Reads live data from HLK-LD2450 radar sensor.
    Drop-in replacement for Simulator — same next_frame() and stream() interface.
    """

    def __init__(self, port: str, baud: int = 256000) -> None:
        self.port  = port
        self.baud  = baud
        self._ser  = None
        self._rx_buf = bytearray()
        self._open()

    def _open(self) -> None:
        try:
            self._ser = serial.Serial(
                port      = self.port,
                baudrate  = self.baud,
                bytesize  = serial.EIGHTBITS,
                parity    = serial.PARITY_NONE,
                stopbits  = serial.STOPBITS_ONE,
                timeout   = 0.05
            )
            print(f"[ld2450] opened {self.port} at {self.baud} baud")
        except serial.SerialException as e:
            raise RuntimeError(
                f"[ld2450] could not open {self.port}\n"
                f"  → {e}\n"
                f"  → run:  ls /dev/cu.usb*  to find your port"
            )

    def _read_frame_bytes(self) -> bytes | None:
        """
        Scans the serial stream for the next valid frame.
        Returns raw 28-byte frame or None on timeout.
        """
        deadline = time.time() + 0.5

        while time.time() < deadline:
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                self._rx_buf.extend(chunk)

            # keep buffer bounded while still preserving enough history
            if len(self._rx_buf) > FRAME_LENGTH * 8:
                del self._rx_buf[:-FRAME_LENGTH * 4]

            while True:
                start = self._rx_buf.find(FRAME_HEADER)
                if start < 0:
                    # Keep just enough tail bytes to catch split header patterns.
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

                # Bad frame alignment: slide by one byte and continue searching.
                del self._rx_buf[0]

        return None

    @staticmethod
    def _parse_target(data: bytes, offset: int) -> Target | None:
        """
        Parses one 8-byte target block starting at offset.
        Returns None if the slot is empty (all zeros).

        LD2450 target format (little-endian):
          bytes 0-1: x     (sign-magnitude uint16, mm; MSB=1 → negative/left)
          bytes 2-3: y     (sign-magnitude uint16, mm; MSB=1 → in front of sensor)
          bytes 4-5: speed (sign-magnitude uint16, cm/s; MSB=1 → moving away)
          bytes 6-7: resolution (uint16, ignored)

        All three measured fields use sign-magnitude encoding (not two's complement).
        Y is negative in the sensor's convention for targets in front; we negate
        it so the dashboard's [0, ROOM_D] y-axis shows forward distance correctly.
        Speed is the Doppler radial velocity computed by the LD2450 internally.
        """
        raw_x, raw_y, raw_v, _ = struct.unpack_from('<HHHH', data, offset)

        def _sm(v: int) -> int:
            """Sign-magnitude decode: MSB is sign bit, lower 15 bits are magnitude."""
            return (-1 if v & 0x8000 else 1) * (v & 0x7FFF)

        x_mm  = _sm(raw_x)
        y_mm  = -_sm(raw_y)   # sensor convention: negative y = in front → negate for display
        v_cms = _sm(raw_v)    # cm/s; negative = moving away from sensor

        # Empty slot
        if x_mm == 0 and y_mm == 0:
            return None

        # Out-of-range: LD2450 max range ~6 m, discard anything beyond 9 m
        if abs(x_mm) > 9000 or abs(y_mm) > 9000:
            return None

        return Target(
            x     = round(x_mm  / 1000.0, 3),   # mm  → metres
            y     = round(y_mm  / 1000.0, 3),
            speed = round(v_cms / 100.0,  3)     # cm/s → m/s
        )

    def next_frame(self) -> Frame:
        """
        Blocks until one valid frame is received.
        Returns a Frame with 0-3 Target objects.
        """
        while True:
            raw = self._read_frame_bytes()
            if raw is None:
                # timeout — return empty frame and try again
                return Frame(targets=[], timestamp=time.time())

            targets = []
            # targets start at byte 4 (after header), 8 bytes each
            for i in range(TARGET_COUNT):
                offset = 4 + i * TARGET_BYTES
                t = self._parse_target(raw, offset)
                if t is not None:
                    targets.append(t)

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