"""Telemetry publisher for remote monitoring."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flower_vending.domain.events import DomainEvent


_logger = logging.getLogger("flower_vending.telemetry")

_MAX_BUFFER = 1000
_FLUSH_INTERVAL_S = 30.0


@dataclass(slots=True)
class TelemetryConfig:
    enabled: bool = False
    endpoint_url: str = ""
    flush_interval_s: float = 30.0
    max_buffer: int = 1000


class TelemetryPublisher:
    def __init__(self, config: TelemetryConfig) -> None:
        self._config = config
        self._buffer: deque[dict[str, Any]] = deque(maxlen=config.max_buffer)
        self._sent_count = 0
        self._dropped_count = 0
        self._last_flush_at: str | None = None

    @property
    def enabled(self) -> bool:
        return self._config.enabled and bool(self._config.endpoint_url)

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    @property
    def sent_count(self) -> int:
        return self._sent_count

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    async def handle_event(self, event: DomainEvent) -> None:
        if not self.enabled:
            return
        entry = {
            "event_type": event.event_type,
            "correlation_id": event.correlation_id,
            "transaction_id": event.transaction_id,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": {k: self._sanitize_value(v) for k, v in event.payload.items()},
        }
        self._buffer.append(entry)

    async def flush(self) -> int:
        if not self.enabled or not self._buffer:
            return 0
        batch = list(self._buffer)
        try:
            sent = await self._send_batch(batch)
            self._sent_count += sent
            for _ in range(sent):
                self._buffer.popleft()
            self._last_flush_at = datetime.now(tz=timezone.utc).isoformat()
            _logger.info("telemetry_flush sent=%d remaining=%d", sent, len(self._buffer))
            return sent
        except Exception as exc:
            _logger.warning("telemetry_flush_failed error=%s", exc)
            if len(self._buffer) >= self._config.max_buffer:
                overage = len(self._buffer) - self._config.max_buffer + len(batch)
                for _ in range(min(overage, len(self._buffer))):
                    self._buffer.popleft()
                    self._dropped_count += 1
            return 0

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        if not self.enabled:
            return
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_FLUSH_INTERVAL_S)
                break
            except asyncio.TimeoutError:
                pass
            if self._buffer:
                await self.flush()

    async def _send_batch(self, batch: list[dict[str, Any]]) -> int:
        payload = json.dumps({"events": batch}, ensure_ascii=False)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(*self._parse_url(self._config.endpoint_url)),
            timeout=10.0,
        )
        try:
            body = payload.encode()
            request = (
                f"POST /api/v1/telemetry HTTP/1.1\r\n"
                f"Host: {self._config.endpoint_url.split('://', 1)[-1].split('/')[0].split(':')[0]}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n"
            )
            writer.write(request.encode() + body)
            await writer.drain()
            response_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            status = int(response_line.decode().split(" ", 2)[1]) if response_line else 0
            return len(batch) if status in (200, 201, 202, 204) else 0
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    def _parse_url(url: str) -> tuple[str, int]:
        host_part = url.split("://", 1)[-1].split("/")[0]
        if ":" in host_part:
            host, port_str = host_part.split(":", 1)
            return host, int(port_str)
        return host_part, 80

    @staticmethod
    def _sanitize_value(value: Any) -> Any:
        if isinstance(value, (int, float, str, bool, type(None))):
            return value
        if isinstance(value, (list, tuple)):
            return [TelemetryPublisher._sanitize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: TelemetryPublisher._sanitize_value(v) for k, v in value.items()}
        return str(value)
