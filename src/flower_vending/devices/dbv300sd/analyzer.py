"""DBV-300-SD Protocol Analyzer & Discovery Tool.

This tool helps figure out the actual JCM protocol frame format
by trying different configurations against a live device.

Usage:
  python -m flower_vending dbv300sd-analyze --port COM3

It will:
  1. Scan common baud rates
  2. Try different frame formats
  3. Report which configuration gets a valid response
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from flower_vending.devices.dbv300sd.transport.serial_transport import SerialDBV300Transport
from flower_vending.devices.dbv300sd.config import SerialTransportSettings


@dataclass
class ProtocolProbeResult:
    port: str
    baudrate: int
    parity: str
    label: str
    tx_hex: str
    rx_hex: str
    rx_len: int
    success: bool = False
    error: str = ""


_BAUD_RATES = [9600, 19200, 38400, 115200]
_PARITIES = ["N", "E", "O"]

# Common JCM/ID-003 probe frames to try
_PROBES = [
    # Format: STX LEN CMD CKSUM ETX (common JCM poll)
    ("STX+LEN+CMD+CKSUM+ETX poll", "02 02 01 01 03"),
    # Alternate: STX LEN CMD DATA CKSUM ETX
    ("STX+LEN+CMD+FF+CKSUM+ETX", "02 03 01 FF 01 03"),
    # Raw poll (no framing)
    ("Raw poll 01", "01"),
    # Ack request
    ("ACK request", "02 02 00 00 03"),
    # Status request
    ("Status request", "02 03 03 00 03 03"),
    # Enable acceptance
    ("Enable acceptance", "02 03 08 01 09 03"),
    # Poll with different checksum
    ("Alt poll", "02 03 01 00 02 03"),
    # Simple command
    ("Simple 5 byte", "02 02 81 81 03"),
    # JCM protocol variant
    ("JCM poll variant", "02 05 01 01 01 05 03"),
]


async def probe_port(
    port: str,
    baudrate: int = 9600,
    parity: str = "N",
    tx_hex: str = "02 02 01 01 03",
    read_size: int = 32,
    timeout_s: float = 0.5,
) -> ProtocolProbeResult:
    settings = SerialTransportSettings(
        port=port,
        baudrate=baudrate,
        parity=parity,
        read_timeout_s=timeout_s,
        write_timeout_s=timeout_s,
    )
    transport = SerialDBV300Transport(settings)
    tx_bytes = bytes.fromhex(tx_hex.replace(" ", ""))
    result = ProtocolProbeResult(
        port=port,
        baudrate=baudrate,
        parity=parity,
        label=f"{baudrate}/{parity}",
        tx_hex=tx_hex,
        rx_hex="",
        rx_len=0,
    )
    try:
        await transport.open()
        await transport.flush_input()
        await transport.write(tx_bytes)
        await asyncio.sleep(0.1)
        rx = await transport.read(read_size)
        result.rx_hex = " ".join(f"{b:02X}" for b in rx)
        result.rx_len = len(rx)
        result.success = len(rx) > 0
        if rx:
            # Check if response looks like a valid frame
            if rx[0] == 0x02 or any(b == 0x02 for b in rx):
                result.success = True
    except Exception as exc:
        result.error = str(exc)
    finally:
        try:
            await transport.close()
        except Exception:
            pass
    return result


async def analyze_port(
    port: str, read_size: int = 32, timeout_s: float = 0.5
) -> list[ProtocolProbeResult]:
    results: list[ProtocolProbeResult] = []

    # Phase 1: Try different baud rates with standard probes
    for baud in _BAUD_RATES:
        for parity in _PARITIES:
            for label, tx_hex in _PROBES[:3]:
                result = await probe_port(
                    port,
                    baudrate=baud,
                    parity=parity,
                    tx_hex=tx_hex,
                    read_size=read_size,
                    timeout_s=timeout_s,
                )
                results.append(result)

    # Phase 2: If any worked, try more probes with that config
    working = [r for r in results if r.success]
    if working:
        best = working[0]
        for label, tx_hex in _PROBES[3:]:
            result = await probe_port(
                port,
                baudrate=best.baudrate,
                parity=best.parity,
                tx_hex=tx_hex,
                read_size=read_size,
                timeout_s=timeout_s,
            )
            results.append(result)

    return results


def format_analysis(results: list[ProtocolProbeResult]) -> str:
    lines = ["=== DBV-300-SD Protocol Analysis ==="]
    working = [r for r in results if r.success]
    lines.append(f"Total probes: {len(results)}, Got response: {len(working)}")

    if working:
        lines.append("\n--- Working configurations ---")
        for r in working:
            lines.append(f"  {r.label}: TX={r.tx_hex} -> RX={r.rx_hex} ({r.rx_len} bytes)")

    lines.append("\n--- All probes ---")
    for r in results:
        status = "✓" if r.success else "✗"
        err = f" [{r.error}]" if r.error else ""
        lines.append(f"  {status} {r.label} | TX={r.tx_hex} | RX={r.rx_hex}{err}")

    return "\n".join(lines)
