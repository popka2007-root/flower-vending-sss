"""Generic serial byte transport for the JCM DBV-300-SD."""

from __future__ import annotations

import asyncio
from types import ModuleType
from typing import Any

from flower_vending.devices.dbv300sd.config import SerialTransportSettings
from flower_vending.devices.dbv300sd.transport.base import DBV300Transport
from flower_vending.devices.exceptions import (
    ConfigurationError,
    DeviceNotStartedError,
    TransportIOError,
)

pyserial: ModuleType | None
try:
    import serial as pyserial
except ImportError:  # pragma: no cover - optional dependency
    pyserial = None


class SerialDBV300Transport(DBV300Transport):
    """Cross-platform serial transport wrapper.

    This class intentionally provides only byte-stream behavior. It does not encode
    any DBV-300-SD protocol commands and is therefore safe to implement before the
    device protocol is confirmed.
    """

    def __init__(self, settings: SerialTransportSettings, serial_module: Any | None = None) -> None:
        self._settings = settings
        self._serial_module = pyserial if serial_module is None else serial_module
        self._port: Any | None = None

    @property
    def name(self) -> str:
        return f"serial:{self._settings.port}"

    @property
    def is_open(self) -> bool:
        return bool(self._port is not None and getattr(self._port, "is_open", False))

    async def open(self) -> None:
        if self.is_open:
            return
        if self._serial_module is None:
            raise ConfigurationError(
                "pyserial is required for serial DBV-300-SD transport but is not installed"
            )
        try:
            self._port = await asyncio.to_thread(
                self._serial_module.Serial,
                port=self._settings.port,
                baudrate=self._settings.baudrate,
                bytesize=self._settings.bytesize,
                parity=self._settings.parity,
                stopbits=self._settings.stopbits,
                timeout=self._settings.read_timeout_s,
                write_timeout=self._settings.write_timeout_s,
            )
        except Exception as exc:  # pragma: no cover - depends on host serial stack
            raise TransportIOError(
                f"failed to open serial transport on {self._settings.port}: {exc}"
            ) from exc

    async def close(self) -> None:
        port = self._port
        if port is None or not getattr(port, "is_open", False):
            self._port = None
            return
        try:
            await asyncio.to_thread(port.close)
        except Exception as exc:  # pragma: no cover - depends on host serial stack
            raise TransportIOError(f"failed to close serial transport: {exc}") from exc
        finally:
            self._port = None

    async def write(self, payload: bytes) -> None:
        port = self._require_port()
        try:
            await asyncio.to_thread(port.write, payload)
            await asyncio.to_thread(port.flush)
        except Exception as exc:  # pragma: no cover - depends on host serial stack
            raise TransportIOError(f"serial write failed on {self.name}: {exc}") from exc

    async def read(self, size: int = 1) -> bytes:
        if size <= 0:
            raise ValueError("size must be positive")
        port = self._require_port()
        try:
            data = await asyncio.to_thread(port.read, size)
        except Exception as exc:  # pragma: no cover - depends on host serial stack
            raise TransportIOError(f"serial read failed on {self.name}: {exc}") from exc
        if not isinstance(data, (bytes, bytearray)):
            raise TransportIOError("serial transport returned a non-bytes payload")
        return bytes(data)

    async def flush_input(self) -> None:
        port = self._require_port()
        try:
            await asyncio.to_thread(port.reset_input_buffer)
        except Exception as exc:  # pragma: no cover - depends on host serial stack
            raise TransportIOError(f"serial input flush failed on {self.name}: {exc}") from exc

    def _require_port(self) -> Any:
        if not self.is_open:
            raise DeviceNotStartedError(f"serial transport {self.name} is not open")
        return self._port
