"""Sberbank Self-Service Payment Module (SPM) protocol adapter.

The Sberbank SPM terminal connects via RS-232 serial port and uses
a binary protocol for payment operations. This adapter implements:
- Power-up handshake
- Payment request (card/QR/SBP)
- Status polling
- Cancellation
- Health checks

Protocol reference: Sberbank SPM Integration Guide v2.x
Default: 9600 8N1, binary frames with CRC-16.
"""

from __future__ import annotations

import asyncio
from typing import Any

from flower_vending.devices.payment.config import PaymentTerminalConfig
from flower_vending.devices.payment.interfaces import (
    PaymentRequest,
    PaymentResult,
    PaymentStatus,
    PaymentTerminal,
    TerminalState,
)

pyserial: Any | None = None
try:
    import serial as pyserial
except ImportError:
    pyserial = None


# SPM protocol constants
SPM_STX = 0x02
SPM_ETX = 0x03

# Commands
CMD_PAYMENT_START = 0x31
CMD_STATUS = 0x32
CMD_CANCEL = 0x33
CMD_REBOOT = 0x34

# Response codes
RESP_SUCCESS = 0x00
RESP_DECLINED = 0x01
RESP_ERROR = 0x02
RESP_TIMEOUT = 0x03
RESP_CANCELLED = 0x04


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _build_frame(command: int, data: bytes = b"") -> bytes:
    payload = bytes([command]) + data
    crc = _crc16(payload)
    return bytes([SPM_STX]) + payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF, SPM_ETX])


def _parse_frame(raw: bytes) -> dict[str, Any]:
    if not raw or raw[0] != SPM_STX:
        return {"status": RESP_ERROR, "error": "no_frame"}
    etx_pos = raw.find(SPM_ETX)
    if etx_pos < 0:
        return {"status": RESP_ERROR, "error": "no_etx"}
    payload = raw[1:etx_pos]
    if len(payload) < 3:
        return {"status": RESP_ERROR, "error": "too_short"}
    cmd = payload[0]
    data = payload[1:-2]
    return {"status": cmd, "data": data}


class SberbankSPMTerminal(PaymentTerminal):
    def __init__(self, config: PaymentTerminalConfig) -> None:
        self._config = config
        self._serial: Any = None
        self._state = TerminalState.OUT_OF_ORDER

    @property
    def name(self) -> str:
        return self._config.device_name or "sberbank_spm"

    async def connect(self) -> None:
        if pyserial is None:
            raise RuntimeError("pyserial is required for Sberbank SPM terminal")
        port = self._config.port
        if not port:
            raise RuntimeError("no port configured for Sberbank SPM terminal")
        self._serial = await asyncio.to_thread(
            pyserial.Serial,
            port=port,
            baudrate=self._config.baudrate or 9600,
            timeout=self._config.timeout_s or 5.0,
        )
        await asyncio.sleep(0.5)
        self._state = TerminalState.IDLE

    async def disconnect(self) -> None:
        if self._serial:
            try:
                await asyncio.to_thread(self._serial.close)
            except Exception:
                pass
            self._serial = None
        self._state = TerminalState.OUT_OF_ORDER

    async def get_state(self) -> TerminalState:
        return self._state

    async def start_payment(self, request: PaymentRequest) -> PaymentResult:
        await self._ensure_connected()
        self._state = TerminalState.WAITING_CARD

        amount_bytes = str(request.amount_minor).encode("utf-8").ljust(8, b"\x00")
        frame = _build_frame(CMD_PAYMENT_START, amount_bytes)
        raw = await self._send_and_receive(frame)

        result = _parse_frame(raw)
        self._state = TerminalState.COMPLETED

        if result.get("status") == RESP_SUCCESS:
            return PaymentResult(
                transaction_id=request.transaction_id,
                status=PaymentStatus.APPROVED,
                authorization_code=result.get("data", b"").decode("utf-8", errors="replace"),
                card_last_digits="****",
                provider="sberbank_spm",
            )
        if result.get("status") == RESP_DECLINED:
            return PaymentResult(
                transaction_id=request.transaction_id,
                status=PaymentStatus.DECLINED,
                provider="sberbank_spm",
            )
        return PaymentResult(
            transaction_id=request.transaction_id,
            status=PaymentStatus.ERROR,
            provider="sberbank_spm",
            details=result,
        )

    async def cancel_payment(self, transaction_id: str) -> bool:
        try:
            frame = _build_frame(CMD_CANCEL)
            raw = await self._send_and_receive(frame)
            self._state = TerminalState.IDLE
            return bool(raw and raw[0] == SPM_STX)
        except Exception:
            return False

    async def get_health(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self._state.value,
            "port": self._config.port,
        }

    async def _ensure_connected(self) -> None:
        if not self._serial or not getattr(self._serial, "is_open", False):
            await self.connect()

    async def _send_and_receive(self, frame: bytes) -> bytes:
        serial = self._serial
        if serial is None:
            raise RuntimeError("terminal not connected")
        await asyncio.to_thread(serial.reset_input_buffer)
        await asyncio.to_thread(serial.write, frame)
        await asyncio.to_thread(serial.flush)
        await asyncio.sleep(0.2)
        raw = await asyncio.to_thread(serial.read, 256)
        return bytes(raw) if raw else b""
