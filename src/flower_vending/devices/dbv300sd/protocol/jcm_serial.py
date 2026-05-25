"""Real JCM DBV-300-SD / ID-003 serial protocol implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

from flower_vending.devices.contracts import (
    BillValidatorEventType,
    MoneyValue,
    ProtocolCapabilities,
    ValidatorProtocolEvent,
)
from flower_vending.devices.dbv300sd.protocol.base import DBV300Protocol
from flower_vending.devices.dbv300sd.transport.base import DBV300Transport
from flower_vending.devices.exceptions import (
    DeviceProtocolError,
)


class JcmCommand(IntEnum):
    POLL = 0x01
    GET_DENOM_TABLE = 0x03
    SET_ACCEPTANCE = 0x08
    STACK_ESCROW = 0x0C
    RETURN_ESCROW = 0x0D


class JcmResponseCode(IntEnum):
    ACK = 0x00
    BILL_INSERTED = 0x80
    BILL_VALIDATED = 0x81
    BILL_REJECTED = 0x82
    BILL_STACKED = 0x83
    ESCROW_POSITION = 0x84
    BILL_RETURNED = 0x85
    STACKER_FULL = 0x86
    BILL_JAM = 0x87
    POWER_UP = 0x90
    COMMAND_TIMEOUT = 0xF0
    COMMAND_ERROR = 0xF1


_DENOMINATION_MAP: dict[int, int] = {
    0x01: 10000,
    0x02: 50000,
    0x03: 100000,
    0x04: 200000,
    0x05: 500000,
    0x06: 1000,
    0x07: 2000,
    0x08: 5000,
}


@dataclass(frozen=True, slots=True)
class JcmFrame:
    command: int
    data: bytes
    payload: bytes


def _xor_checksum(data: bytes) -> int:
    cksum = 0
    for byte in data:
        cksum ^= byte
    return cksum


def _build_frame(command: int, data: bytes = b"") -> bytes:
    cmd_data = bytes([command]) + data
    cksum = _xor_checksum(cmd_data)
    length = len(cmd_data) + 1
    return bytes([0x02, length]) + cmd_data + bytes([cksum, 0x03])


def _parse_frames(data: bytes) -> list[JcmFrame]:
    frames: list[JcmFrame] = []
    i = 0
    while i < len(data):
        if data[i] != 0x02:
            i += 1
            continue
        if i + 3 >= len(data):
            break
        length = data[i + 1]
        etx_pos = i + 2 + length
        if etx_pos >= len(data) or data[etx_pos] != 0x03:
            i += 1
            continue
        cmd_data = data[i + 2 : etx_pos]
        cksum_byte = cmd_data[-1]
        cmd = cmd_data[0]
        payload = cmd_data[1:-1]
        expected_cksum = _xor_checksum(cmd_data[:-1])
        if cksum_byte != expected_cksum:
            i = etx_pos + 1
            continue
        frames.append(JcmFrame(command=cmd, data=payload, payload=data[i : etx_pos + 1]))
        i = etx_pos + 1
    return frames


@dataclass(frozen=True, slots=True)
class JcmProtocolConfig:
    poll_interval_s: float = 0.2
    read_timeout_s: float = 0.2
    response_max_bytes: int = 64
    denomination_map: dict[int, int] | None = None


class JCMSerialDBV300Protocol(DBV300Protocol):
    def __init__(
        self,
        config: JcmProtocolConfig | None = None,
    ) -> None:
        self._config = config or JcmProtocolConfig()
        self._denom_map = self._config.denomination_map or _DENOMINATION_MAP
        self._sequence: int = 0

    @property
    def name(self) -> str:
        return "jcm-dbv300-serial-v1"

    @property
    def capabilities(self) -> ProtocolCapabilities:
        return ProtocolCapabilities(
            escrow_supported=True,
            polling_required=True,
            push_events_supported=False,
        )

    async def initialize(self, transport: DBV300Transport) -> None:
        if not transport.is_open:
            raise DeviceProtocolError("transport must be opened before protocol init")
        await transport.flush_input()
        frames = await self._send_command(transport, JcmCommand.POLL, max_responses=2)
        if not frames:
            raise DeviceProtocolError("no response from validator during init")

    async def shutdown(self, transport: DBV300Transport) -> None:
        try:
            await self.set_acceptance_enabled(transport, False)
        except Exception:
            pass
        try:
            await transport.flush_input()
        except Exception:
            pass

    async def set_acceptance_enabled(self, transport: DBV300Transport, enabled: bool) -> None:
        data = bytes([0x01 if enabled else 0x00])
        frames = await self._send_command(transport, JcmCommand.SET_ACCEPTANCE, data=data)
        if frames and frames[0].command != JcmResponseCode.ACK:
            raise DeviceProtocolError(
                f"set_acceptance({enabled}) failed: response=0x{frames[0].command:02X}"
            )

    async def poll(self, transport: DBV300Transport) -> Sequence[ValidatorProtocolEvent]:
        frames = await self._send_command(transport, JcmCommand.POLL)
        if not frames:
            return []
        events: list[ValidatorProtocolEvent] = []
        for frame in frames:
            event = self._translate_frame(frame)
            if event is not None:
                events.append(event)
        return events

    async def stack_escrow(self, transport: DBV300Transport) -> None:
        frames = await self._send_command(transport, JcmCommand.STACK_ESCROW)
        if frames and frames[0].command not in (JcmResponseCode.ACK, JcmResponseCode.BILL_STACKED):
            msg = f"stack_escrow failed: response=0x{frames[0].command:02X}"
            raise DeviceProtocolError(msg)

    async def return_escrow(self, transport: DBV300Transport) -> None:
        frames = await self._send_command(transport, JcmCommand.RETURN_ESCROW)
        if frames and frames[0].command not in (JcmResponseCode.ACK, JcmResponseCode.BILL_RETURNED):
            msg = f"return_escrow failed: response=0x{frames[0].command:02X}"
            raise DeviceProtocolError(msg)

    async def _send_command(
        self,
        transport: DBV300Transport,
        command: JcmCommand,
        data: bytes = b"",
        max_responses: int = 5,
    ) -> list[JcmFrame]:
        frame = _build_frame(command.value, data)
        self._sequence += 1
        await transport.write(frame)
        await asyncio.sleep(0.05)
        raw = await transport.read(self._config.response_max_bytes)
        if not raw:
            return []
        return _parse_frames(raw)

    def _translate_frame(self, frame: JcmFrame) -> ValidatorProtocolEvent | None:
        cmd = frame.command
        denom_code = frame.data[0] if frame.data else 0
        bill_value = self._denom_to_value(denom_code)

        if cmd == JcmResponseCode.ACK:
            return None
        if cmd == JcmResponseCode.BILL_INSERTED:
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.BILL_DETECTED,
                bill_value=bill_value,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"denomination_code": denom_code},
            )
        if cmd == JcmResponseCode.BILL_VALIDATED:
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.BILL_VALIDATED,
                bill_value=bill_value,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"denomination_code": denom_code},
            )
        if cmd == JcmResponseCode.BILL_REJECTED:
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.BILL_REJECTED,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"denomination_code": denom_code},
            )
        if cmd == JcmResponseCode.BILL_STACKED:
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.BILL_STACKED,
                bill_value=bill_value,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"denomination_code": denom_code},
            )
        if cmd == JcmResponseCode.ESCROW_POSITION:
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.ESCROW_AVAILABLE,
                bill_value=bill_value,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"denomination_code": denom_code},
            )
        if cmd == JcmResponseCode.BILL_RETURNED:
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.BILL_RETURNED,
                bill_value=bill_value,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"denomination_code": denom_code},
            )
        if cmd == JcmResponseCode.STACKER_FULL:
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.VALIDATOR_FAULT,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"fault": "stacker_full", "denomination_code": denom_code},
            )
        if cmd == JcmResponseCode.BILL_JAM:
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.VALIDATOR_FAULT,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"fault": "bill_jam", "denomination_code": denom_code},
            )
        if cmd == JcmResponseCode.POWER_UP:
            return None
        if cmd in (JcmResponseCode.COMMAND_TIMEOUT, JcmResponseCode.COMMAND_ERROR):
            return ValidatorProtocolEvent(
                event_type=BillValidatorEventType.VALIDATOR_FAULT,
                raw_payload=frame.payload,
                sequence_number=self._sequence,
                details={"fault": f"protocol_error_0x{cmd:02X}"},
            )
        return None

    def _denom_to_value(self, code: int) -> MoneyValue | None:
        minor = self._denom_map.get(code)
        if minor is None:
            return None
        return MoneyValue(minor_units=minor, currency="RUB")
