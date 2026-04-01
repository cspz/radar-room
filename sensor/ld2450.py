"""
sensor/ld2450.py
Real LD2450 hardware parser.
Reads binary frames from the sensor over UART and outputs
the same Frame + Target objects as the simulator.

Protocol reference: HLK-LD2450 datasheet
  - Frame header:  FD FC FB FA  (4 bytes)
  - Frame footer:  04 03 02 01  (4 bytes)
  - Frame length:  30 bytes total
  - Up to 3 targets per frame, each 8 bytes
"""

import serial
import struct
import time
from dataclasses import dataclass
from typing import Generator

from sensor.simulator import Target, Frame   # reuse same data structures


# ── Protocol constants ────────────────────────────────────────────────────────

FRAME_HEADER = bytes([0xFD, 0xFC, 0xFB, 0xFA])
FRAME_FOOTER = bytes([0x04, 0x03, 0x02, 0x01])
FRAME_LENGTH = 30          # total bytes per frame
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
        self._open()

    def _open(self) -> None:
        try:
            self._ser = serial.Serial(
                port      = self.port,
                baudrate  = self.baud,
                bytesize  = serial.EIGHTBITS,
                parity    = serial.PARITY_NONE,
                stopbits  = serial.STOPBITS_ONE,
                timeout   = 1.0
            )
            print(f"[ld2450] opened {self.port} at {self.baud} baud")
        except serial.SerialException as e:
            raise RuntimeError(
                f"[ld2450] could not open {self.port}\n"
                f"  → {e}\n"
                f"  → run:  ls /dev/tty.usb*  to find your port"
            )

    def _read_frame_bytes(self) -> bytes | None:
        """
        Scans the serial stream for the next valid frame.
        Returns raw 30-byte frame or None on timeout.
        """
        buf = b''
        deadline = time.time() + 2.0   # 2 second timeout

        while time.time() < deadline:
            byte = self._ser.read(1)
            if not byte:
                continue
            buf += byte

            # keep buffer trimmed
            if len(buf) > FRAME_LENGTH * 2:
                buf = buf[-FRAME_LENGTH:]

            # look for header
            if FRAME_HEADER in buf:
                start = buf.index(FRAME_HEADER)
                buf   = buf[start:]           # trim everything before header

                # wait until we have a full frame
                if len(buf) >= FRAME_LENGTH:
                    candidate = buf[:FRAME_LENGTH]
                    # verify footer
                    if candidate[-4:] == FRAME_FOOTER:
                        return candidate
                    else:
                        # bad frame — discard header byte and try again
                        buf = buf[1:]

        return None   # timeout

    @staticmethod
    def _parse_target(data: bytes, offset: int) -> Target | None:
        """
        Parses one 8-byte target block starting at offset.
        Returns None if target is empty (all zeros).

        LD2450 target format (little-endian):
          bytes 0-1: x  (signed int16, millimetres)
          bytes 2-3: y  (signed int16, millimetres)
          bytes 4-5: speed (signed int16, mm/s)
          bytes 6-7: resolution (uint16, ignored)
        """
        x_mm, y_mm, v_mm, _ = struct.unpack_from('<hhhH', data, offset)

        if x_mm == 0 and y_mm == 0 and v_mm == 0:
            return None   # empty slot

        return Target(
            x     = round(x_mm / 1000.0, 3),   # mm → metres
            y     = round(y_mm / 1000.0, 3),
            speed = round(v_mm / 1000.0, 3)
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