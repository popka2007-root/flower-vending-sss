"""Receipt printer adapter for VKP80II / ESC/POS over USB serial."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType
from typing import Any

from flower_vending.devices.exceptions import ConfigurationError, DeviceAdapterError

pyserial: ModuleType | None
try:
    import serial as pyserial
except ImportError:
    pyserial = None


@dataclass(frozen=True, slots=True)
class PrinterAdapterConfig:
    port: str = ""
    baudrate: int = 19200
    timeout_s: float = 2.0
    vendor_id: str | None = None
    product_id: str | None = None


_PRINT_HEADER = [
    "\x1b\x40",
    "\x1b\x61\x01",
    "\x1b\x21\x30",
    "FLOWER VENDING\n",
    "\x1b\x21\x00",
    "\x1b\x61\x01",
    "====================\n",
]

_PRINT_FOOTER = [
    "====================\n",
    "\x1b\x61\x00",
    "\x1b\x64\x02",
    "\x1b\x64\x02",
]


class PrinterAdapter:
    def __init__(self, config: PrinterAdapterConfig) -> None:
        self._config = config
        self._serial: Any | None = None

    @property
    def is_connected(self) -> bool:
        return bool(self._serial and getattr(self._serial, "is_open", False))

    async def connect(self) -> None:
        if self.is_connected:
            return
        if pyserial is None:
            raise ConfigurationError("pyserial is required for printer support")
        port = self._config.port
        if not port:
            port = self._discover_printer()
        if not port:
            raise ConfigurationError("no printer port found")
        try:
            self._serial = await asyncio.to_thread(
                pyserial.Serial,
                port=port,
                baudrate=self._config.baudrate,
                timeout=self._config.timeout_s,
            )
            await asyncio.sleep(0.5)
        except Exception as exc:
            raise DeviceAdapterError(f"printer connect failed on {port}: {exc}") from exc

    async def disconnect(self) -> None:
        if self._serial:
            try:
                await asyncio.to_thread(self._serial.close)
            except Exception:
                pass
            self._serial = None

    def _require_serial(self) -> Any:
        if self._serial is None:
            raise DeviceAdapterError("printer is not connected")
        return self._serial

    async def print_receipt(
        self,
        items: list[dict[str, Any]],
        total_minor: int,
        payment_minor: int,
        change_minor: int = 0,
        currency: str = "RUB",
    ) -> None:
        if not self.is_connected:
            return
        lines: list[str] = []
        lines.extend(_PRINT_HEADER)
        now = datetime.now()
        lines.append(f"{now.strftime('%d.%m.%Y %H:%M')}\n")
        lines.append("--------------------\n")
        for item in items:
            name = item.get("display_name", item.get("name", "?"))
            price = f"{item.get('price_minor_units', 0) / 100:.2f}"
            lines.append(f"\x1b\x61\x00{name}\n")
            lines.append(f"\x1b\x61\x01{price} RUB\n")
        lines.append("--------------------\n")
        lines.append(f"\x1b\x21\x20ИТОГО: {total_minor / 100:.2f} RUB\n")
        lines.append(f"\x1b\x21\x00ОПЛАЧЕНО: {payment_minor / 100:.2f} RUB\n")
        if change_minor > 0:
            lines.append(f"СДАЧА: {change_minor / 100:.2f} RUB\n")
        lines.extend(_PRINT_FOOTER)
        try:
            data = "".join(lines).encode("cp866", errors="replace")
            serial = self._require_serial()
            await asyncio.to_thread(serial.write, data)
            await asyncio.to_thread(serial.flush)
        except Exception as exc:
            raise DeviceAdapterError(f"printer write failed: {exc}") from exc

    async def print_test(self) -> None:
        lines = [
            "\x1b\x40",
            "\x1b\x61\x01",
            "PRINTER TEST\n",
            "\x1b\x21\x00",
            "====================\n",
            "Flower Vending System\n",
            f"Date: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n",
            "--------------------\n",
            "Если вы это читаете -\n",
            "принтер работает!\n",
            "====================\n",
            "\x1b\x64\x04",
        ]
        if not self.is_connected:
            await self.connect()
        serial = self._require_serial()
        data = "".join(lines).encode("cp866", errors="replace")
        await asyncio.to_thread(serial.write, data)
        await asyncio.to_thread(serial.flush)

    def _discover_printer(self) -> str:
        if pyserial is None:
            return ""
        try:
            import serial.tools.list_ports as lp

            for p in lp.comports():
                desc = (p.description + " " + p.hwid).lower()
                if "vkp" in desc or "printer" in desc or "pos" in desc:
                    return p.device
                if self._config.vendor_id and self._config.vendor_id.lower() in p.hwid.lower():
                    return p.device
        except Exception:
            pass
        return ""
