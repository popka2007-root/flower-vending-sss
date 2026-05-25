"""Auto-discovery tools for Arduino/ESP32 and DBV-300-SD COM ports."""

from __future__ import annotations

import asyncio
from typing import Any


def find_esp32_port() -> str | None:
    """Find ESP32 by scanning COM ports."""
    try:
        import serial.tools.list_ports as lp

        for port in lp.comports():
            desc = (port.description + " " + port.hwid).lower()
            if "cp210" in desc or "ch34" in desc or "silab" in desc:
                return port.device
    except Exception:
        pass
    return None


def find_jcm_port() -> str | None:
    """Attempt to find JCM DBV-300-SD on COM ports."""
    try:
        import serial.tools.list_ports as lp

        for port in lp.comports():
            desc = (port.description + " " + port.hwid).lower()
            if "jcm" in desc or "dbv" in desc:
                return port.device
    except Exception:
        pass
    return None


def list_com_ports() -> list[dict[str, str]]:
    """List all available COM ports with descriptions."""
    result: list[dict[str, str]] = []
    try:
        import serial.tools.list_ports as lp

        for port in lp.comports():
            result.append(
                {
                    "device": port.device,
                    "description": port.description,
                    "hwid": port.hwid,
                    "manufacturer": port.manufacturer or "",
                }
            )
    except Exception:
        pass
    return result


async def discover_arduino() -> dict[str, Any]:
    """Discover Arduino/ESP32 by sending STATUS command."""
    ports = list_com_ports()
    for info in ports:
        try:
            import serial as ser

            s = ser.Serial(
                port=info["device"],
                baudrate=115200,
                timeout=1.0,
                write_timeout=0.5,
            )
            await asyncio.sleep(0.3)
            s.write(b"STATUS\n")
            await asyncio.sleep(0.1)
            response = b""
            try:
                response = s.readline()
            except Exception:
                pass
            s.close()
            if b"BUTTON" in response or b"DRUM" in response:
                return {
                    "port": info["device"],
                    "description": info["description"],
                    "response": response.decode("utf-8", errors="replace").strip(),
                    "type": "arduino_esp32",
                }
        except Exception:
            continue
    return {"port": "", "description": "not found", "response": "", "type": "unknown"}


def format_discovery(results: dict[str, Any]) -> str:
    lines = [
        "--- COM Port Discovery ---",
    ]
    if results.get("port"):
        lines.append(f"ESP32 found on: {results['port']}")
        lines.append(f"Description: {results['description']}")
        lines.append(f"Status response: {results['response']}")
    else:
        lines.append("ESP32 not found. Available ports:")
        for port in list_com_ports():
            lines.append(f"  {port['device']}: {port['description']} ({port['hwid']})")
    return "\n".join(lines)
