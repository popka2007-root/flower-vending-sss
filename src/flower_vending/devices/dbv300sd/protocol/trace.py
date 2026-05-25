"""Protocol trace recording for DBV-300-SD bench validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import TextIOWrapper
from pathlib import Path
from typing import Literal

TraceDirection = Literal["rx", "tx"]


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def format_bytes_hex(payload: bytes) -> str:
    """Return a stable, human-scannable hex representation for raw bytes."""
    return " ".join(f"{byte:02X}" for byte in payload)


@dataclass(frozen=True, slots=True)
class ProtocolTraceRecord:
    timestamp: datetime
    direction: TraceDirection
    raw_bytes_hex: str
    correlation_id: str | None = None
    note: str | None = None

    @classmethod
    def from_payload(
        cls,
        *,
        direction: TraceDirection,
        payload: bytes,
        correlation_id: str | None = None,
        note: str | None = None,
        timestamp: datetime | None = None,
    ) -> "ProtocolTraceRecord":
        return cls(
            timestamp=_utc_now() if timestamp is None else timestamp,
            direction=direction,
            raw_bytes_hex=format_bytes_hex(payload),
            correlation_id=correlation_id,
            note=note,
        )

    def to_json_payload(self) -> dict[str, str | None]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction,
            "raw_bytes_hex": self.raw_bytes_hex,
            "correlation_id": self.correlation_id,
            "note": self.note,
        }


@dataclass(slots=True)
class ProtocolTraceRecorder:
    """Append-only JSONL recorder for raw protocol frame analysis."""

    path: Path
    _records: list[ProtocolTraceRecord] = field(default_factory=list, init=False)
    _handle: TextIOWrapper | None = field(init=False, default=None)

    @property
    def records(self) -> tuple[ProtocolTraceRecord, ...]:
        return tuple(self._records)

    def _ensure_open(self) -> None:
        if self._handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")

    def record(
        self,
        *,
        direction: TraceDirection,
        payload: bytes,
        correlation_id: str | None = None,
        note: str | None = None,
    ) -> ProtocolTraceRecord:
        record = ProtocolTraceRecord.from_payload(
            direction=direction,
            payload=payload,
            correlation_id=correlation_id,
            note=note,
        )
        self._ensure_open()
        if self._handle is None:
            raise RuntimeError(f"trace recorder failed to open {self.path}")
        self._handle.write(json.dumps(record.to_json_payload(), ensure_ascii=False) + "\n")
        self._records.append(record)
        return record

    def flush(self) -> None:
        if self._handle is not None:
            self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __del__(self) -> None:
        self.close()

    def record_rx(
        self,
        payload: bytes,
        *,
        correlation_id: str | None = None,
        note: str | None = None,
    ) -> ProtocolTraceRecord:
        return self.record(
            direction="rx",
            payload=payload,
            correlation_id=correlation_id,
            note=note,
        )

    def record_tx(
        self,
        payload: bytes,
        *,
        correlation_id: str | None = None,
        note: str | None = None,
    ) -> ProtocolTraceRecord:
        return self.record(
            direction="tx",
            payload=payload,
            correlation_id=correlation_id,
            note=note,
        )
