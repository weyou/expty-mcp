import logging
from typing import Any

import serial
import serial.tools.list_ports

from .base import BaseTransport

logger = logging.getLogger(__name__)


def list_serial_ports() -> list[dict[str, Any]]:
    """Enumerate all connected physical and virtual serial ports on the host."""
    ports = serial.tools.list_ports.comports()
    results = []
    for p in ports:
        results.append(
            {
                "device": p.device,
                "name": p.name,
                "description": p.description,
                "hwid": p.hwid,
                "vid": f"0x{p.vid:04x}" if p.vid else None,
                "pid": f"0x{p.pid:04x}" if p.pid else None,
                "manufacturer": p.manufacturer,
            }
        )
    return results


class SerialTransport(BaseTransport):
    """
    Serial/UART hardware transport for embedded Linux boards, routers, and microcontrollers.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200, timeout: float = 0.05):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: serial.Serial | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=1.0,
            )
        except Exception as e:
            self.ser = None
            raise ConnectionError(f"Failed to open serial port '{self.port}': {e}") from e

    def read(self, max_bytes: int = 4096) -> bytes:
        data, _ = self.read_with_timestamp(max_bytes=max_bytes)
        return data

    def read_with_timestamp(self, max_bytes: int = 4096) -> tuple[bytes, float]:
        import time

        if not self.ser or not self.ser.is_open:
            raise EOFError(f"Serial port '{self.port}' is closed")
        try:
            in_wait = self.ser.in_waiting
            if in_wait > 0:
                data = self.ser.read(min(in_wait, max_bytes))
                return data, time.time()
            return b"", time.time()
        except (serial.SerialException, OSError) as e:
            raise EOFError(f"Serial read error on '{self.port}': {e}") from e

    def write(self, data: bytes) -> int:
        if not self.ser or not self.ser.is_open:
            raise RuntimeError(f"Serial port '{self.port}' is disconnected")
        bytes_written = self.ser.write(data)
        self.ser.flush()
        return bytes_written

    def is_alive(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def get_exit_status(self) -> int | None:
        return None

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception as e:
                logger.debug("Error closing serial port: %s", e)
            finally:
                self.ser = None

    @property
    def display_name(self) -> str:
        status = "open" if self.is_alive() else "closed"
        return f"Serial[{self.port} @ {self.baudrate}bps] ({status})"
