"""Serial transport for Arduino/ESP32 communication with proper protocol."""

from __future__ import annotations

import asyncio
from types import ModuleType
from typing import Any

from flower_vending.devices.exceptions import (
    ConfigurationError,
    DeviceAdapterError,
    DeviceNotStartedError,
    TransportIOError,
)

pyserial: ModuleType | None
try:
    import serial as pyserial
except ImportError:
    pyserial = None


class ArduinoProtocolError(DeviceAdapterError):
    """Raised when Arduino responds with an error."""


class ArduinoSerialTransport:
    def __init__(
        self,
        port: str = "",
        baudrate: int = 115200,
        *,
        read_timeout_s: float = 1.0,
        write_timeout_s: float = 0.5,
        cmd_timeout_s: float = 3.0,
        serial_module: Any | None = None,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._read_timeout_s = read_timeout_s
        self._write_timeout_s = write_timeout_s
        self._cmd_timeout_s = cmd_timeout_s
        self._serial_module = (
            pyserial if serial_module is None and pyserial is not None else serial_module
        )
        self._serial: Any | None = None
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._ready_event = asyncio.Event()

    @property
    def name(self) -> str:
        if self._port:
            return f"arduino:serial:{self._port}"
        return "arduino:serial:auto"

    @property
    def is_open(self) -> bool:
        return bool(self._serial is not None and getattr(self._serial, "is_open", False))

    @property
    def port(self) -> str:
        return self._port

    async def open(self) -> None:
        if self.is_open:
            return
        if self._serial_module is None:
            raise ConfigurationError("pyserial is required but not installed")
        if not self._port:
            discovered = await asyncio.to_thread(self._discover_port)
            if not discovered:
                raise ConfigurationError("no Arduino port found")
            self._port = discovered
        try:
            self._serial = await asyncio.to_thread(
                self._serial_module.Serial,
                port=self._port,
                baudrate=self._baudrate,
                timeout=self._read_timeout_s,
                write_timeout=self._write_timeout_s,
            )
            await asyncio.sleep(0.5)
            await self.flush_input()
            if not await self._ping():
                raise TransportIOError(f"Arduino not responding on {self._port}")
            self._ready_event.set()
        except Exception as exc:
            raise TransportIOError(f"failed to open Arduino on {self._port}: {exc}") from exc

    async def close(self) -> None:
        serial = self._serial
        if serial is None:
            return
        self._ready_event.clear()
        try:
            await asyncio.to_thread(serial.close)
        except Exception:
            pass
        finally:
            self._serial = None

    async def wait_ready(self, timeout_s: float = 10.0) -> None:
        await asyncio.wait_for(self._ready_event.wait(), timeout=timeout_s)

    async def command(self, cmd: str, timeout_s: float | None = None) -> str:
        payload = cmd.strip().upper() + "\n"
        data = payload.encode("utf-8")
        timeout = timeout_s or self._cmd_timeout_s

        async with self._lock:
            serial = self._require_serial()
            try:
                await asyncio.to_thread(serial.reset_input_buffer)
                await asyncio.to_thread(serial.write, data)
                await asyncio.to_thread(serial.flush)
            except Exception as exc:
                raise TransportIOError(f"arduino write failed: {exc}") from exc

            deadline = asyncio.get_event_loop().time() + timeout
            response_lines: list[str] = []
            while asyncio.get_event_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(serial.readline),
                        timeout=max(0.1, deadline - asyncio.get_event_loop().time()),
                    )
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    response_lines.append(line)
                    if line.startswith("OK") or line.startswith("ERR"):
                        result = "\n".join(response_lines)
                        if line.startswith("ERR"):
                            raise ArduinoProtocolError(result)
                        return result
                except asyncio.TimeoutError:
                    break
                except ArduinoProtocolError:
                    raise
                except Exception as exc:
                    raise TransportIOError(f"arduino read failed: {exc}") from exc

            if response_lines:
                return "\n".join(response_lines)
            raise TransportIOError(f"arduino command timed out after {timeout}s: {cmd}")

    async def command_status(self) -> dict[str, str]:
        resp = await self.command("STATUS")
        result: dict[str, str] = {}
        for part in resp.replace("OK ", "").split():
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.lower()] = v
        return result

    async def flush_input(self) -> None:
        serial = self._require_serial()
        try:
            await asyncio.to_thread(serial.reset_input_buffer)
        except Exception:
            pass

    async def _ping(self) -> bool:
        try:
            await self.flush_input()
            raw = await self._raw_write_read(b"INFO\n", timeout_s=1.0)
            return "ESP32_VENDING" in raw or "BUTTON" in raw
        except Exception:
            return False

    async def _raw_write_read(self, data: bytes, timeout_s: float = 1.0) -> str:
        serial = self._require_serial()
        await asyncio.to_thread(serial.reset_input_buffer)
        await asyncio.to_thread(serial.write, data)
        await asyncio.to_thread(serial.flush)
        deadline = asyncio.get_event_loop().time() + timeout_s
        lines: list[str] = []
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(serial.readline),
                    timeout=0.2,
                )
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
            except asyncio.TimeoutError:
                break
            except Exception:
                break
        return "\n".join(lines)

    def _discover_port(self) -> str:
        import sys

        if self._serial_module is None:
            return ""
        if sys.platform != "win32":
            import glob

            candidates = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
            return candidates[0] if candidates else ""
        try:
            import serial.tools.list_ports as lp

            for port in lp.comports():
                desc = (port.description + " " + port.hwid).lower()
                if any(kw in desc for kw in ("cp210", "ch34", "silab", "ftdi")):
                    return port.device
            for port in lp.comports():
                if "USB" in port.hwid or "USB" in port.description:
                    return port.device
        except Exception:
            pass
        return ""

    def _require_serial(self) -> Any:
        if not self.is_open:
            raise DeviceNotStartedError("Arduino transport is not open")
        return self._serial


def find_arduino_port() -> str:
    try:
        import serial.tools.list_ports as lp

        for p in lp.comports():
            desc = (p.description + " " + p.hwid).lower()
            if any(kw in desc for kw in ("cp210", "ch34", "silab", "ftdi")):
                return p.device
        ports = [p.device for p in lp.comports() if "USB" in p.hwid]
        return ports[0] if ports else ""
    except Exception:
        return ""
