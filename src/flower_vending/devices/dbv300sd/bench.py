"""Bench-only helpers for safe DBV-300-SD serial transport smoke checks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flower_vending.devices.dbv300sd.config import SerialTransportSettings
from flower_vending.devices.dbv300sd.protocol.trace import ProtocolTraceRecorder
from flower_vending.devices.dbv300sd.transport.serial_transport import SerialDBV300Transport
from flower_vending.devices.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class SerialSmokeResult:
    transport_name: str
    trace_log: Path
    serial_settings: SerialTransportSettings
    opened: bool
    wrote_bytes: int = 0
    read_bytes: int = 0
    rx_payload: bytes = b""
    note: str = ""

    def to_json_payload(self) -> dict[str, Any]:
        return {
            "transport_name": self.transport_name,
            "trace_log": str(self.trace_log),
            "serial_settings": asdict(self.serial_settings),
            "opened": self.opened,
            "wrote_bytes": self.wrote_bytes,
            "read_bytes": self.read_bytes,
            "rx_payload_hex": " ".join(f"{byte:02X}" for byte in self.rx_payload),
            "note": self.note,
        }


class DBV300SDSerialSmokeBench:
    """Open a serial transport and optionally exchange user-supplied raw bytes."""

    def __init__(
        self,
        *,
        settings: SerialTransportSettings,
        trace_log: Path,
        serial_module: Any | None = None,
    ) -> None:
        self._settings = settings
        self._trace_log = trace_log
        self._transport = SerialDBV300Transport(settings=settings, serial_module=serial_module)
        self._recorder = ProtocolTraceRecorder(trace_log)

    async def run(
        self,
        *,
        tx_payload: bytes | None = None,
        read_size: int = 0,
        correlation_id: str | None = None,
        note: str | None = None,
        flush_input: bool = True,
    ) -> SerialSmokeResult:
        if read_size < 0:
            raise ConfigurationError("read_size must be zero or positive")
        if read_size > 0 and tx_payload is None:
            raise ConfigurationError("read_size requires explicit tx_payload raw bytes")

        self._append_serial_settings(correlation_id=correlation_id, note=note)
        await self._transport.open()
        wrote_bytes = 0
        rx_payload = b""
        try:
            if tx_payload is None:
                return SerialSmokeResult(
                    transport_name=self._transport.name,
                    trace_log=self._trace_log,
                    serial_settings=self._settings,
                    opened=True,
                    note="opened and closed serial transport; no raw bytes were supplied",
                )

            if flush_input:
                await self._transport.flush_input()
            await self._transport.write(tx_payload)
            wrote_bytes = len(tx_payload)
            self._recorder.record_tx(
                tx_payload,
                correlation_id=correlation_id,
                note=note or "bench serial smoke tx",
            )
            if read_size > 0:
                rx_payload = await self._transport.read(read_size)
                self._recorder.record_rx(
                    rx_payload,
                    correlation_id=correlation_id,
                    note="bench serial smoke rx after explicit tx",
                )
            return SerialSmokeResult(
                transport_name=self._transport.name,
                trace_log=self._trace_log,
                serial_settings=self._settings,
                opened=True,
                wrote_bytes=wrote_bytes,
                read_bytes=len(rx_payload),
                rx_payload=rx_payload,
                note="explicit raw byte smoke exchange completed",
            )
        finally:
            await self._transport.close()
            self._recorder.close()

    def _append_serial_settings(
        self,
        *,
        correlation_id: str | None = None,
        note: str | None = None,
    ) -> None:
        self._trace_log.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "event": "serial_parameters",
            "serial_settings": asdict(self._settings),
            "correlation_id": correlation_id,
            "note": note,
        }
        with self._trace_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_hex_bytes(raw: str) -> bytes:
    """Parse explicit operator-provided hex bytes for bench smoke use."""
    normalized = raw.replace(",", " ").replace(":", " ").replace("-", " ")
    tokens = [token.removeprefix("0x").removeprefix("0X") for token in normalized.split()]
    if not tokens:
        raise ConfigurationError("raw byte payload must not be empty")
    try:
        return bytes(int(token, 16) for token in tokens)
    except ValueError as exc:
        raise ConfigurationError(f"invalid hex byte payload: {raw}") from exc
