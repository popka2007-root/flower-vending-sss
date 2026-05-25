"""1C:Enterprise integration client with retry and offline buffering."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from flower_vending.domain.entities import Transaction


_logger = logging.getLogger("flower_vending.integration.1c")

_MAX_ATTEMPTS = 3
_BASE_BACKOFF_S = 1.0


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class _HttpTransport(Protocol):
    async def post(self, url: str, json_payload: dict[str, Any]) -> tuple[int, dict[str, Any]]: ...
    async def get(self, url: str) -> tuple[int, dict[str, Any]]: ...


@dataclass(slots=True)
class OneCConfig:
    enabled: bool = False
    base_url: str = "http://localhost:8080/1c/hs/flower-vending"
    username: str = ""
    password: str = ""
    timeout_s: float = 30.0
    retry_count: int = 3

    inventory_sync_interval_s: float = 300.0
    sales_export_interval_s: float = 60.0
    price_update_interval_s: float = 600.0

    export_sales: bool = True
    import_prices: bool = True
    import_inventory: bool = True
    report_device_status: bool = True


@dataclass(slots=True)
class OneCSyncStatus:
    connected: bool = False
    last_inventory_sync_at: str | None = None
    last_sales_export_at: str | None = None
    last_price_update_at: str | None = None
    last_error: str | None = None
    pending_sales_count: int = 0
    pending_inventory_count: int = 0


class AsyncioHttpTransport:
    """Minimal async HTTP transport using asyncio streams (zero external deps)."""

    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._auth_header: str | None = None

    def set_basic_auth(self, username: str, password: str) -> None:
        import base64

        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._auth_header = f"Basic {credentials}"

    async def post(self, path: str, json_payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return await self._request("POST", path, json_payload)

    async def get(self, path: str) -> tuple[int, dict[str, Any]]:
        return await self._request("GET", path)

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        url = self._base_url
        host_part = url.replace("http://", "").replace("https://", "")
        if ":" in host_part:
            host, port_str = host_part.split(":", 1)
            port = int(port_str)
        else:
            host = host_part
            port = 80

        body_bytes = json.dumps(body, ensure_ascii=False).encode() if body else None
        headers = []
        host_header_set = False
        for line in self._build_headers(method, path, body_bytes):
            headers.append(line.encode())
            if line.lower().startswith("host:"):
                host_header_set = True
        if not host_header_set:
            headers.append(f"Host: {host}".encode())

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self._timeout_s,
            )
        except Exception as exc:
            _logger.warning("1c_connection_failed host=%s error=%s", host, exc)
            return 0, {"error": str(exc)}

        try:
            writer.write(b"\r\n".join(headers) + b"\r\n\r\n")
            if body_bytes:
                writer.write(body_bytes)
            await writer.drain()

            response_line = await asyncio.wait_for(reader.readline(), timeout=self._timeout_s)
            status_code = self._parse_status(response_line.decode().strip())

            headers_raw: list[bytes] = []
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=self._timeout_s)
                if not line or line.strip() == b"":
                    break
                headers_raw.append(line)

            content_length = 0
            for h in headers_raw:
                hl = h.decode().lower()
                if hl.startswith("content-length:"):
                    content_length = int(hl.split(":", 1)[1].strip())

            body_raw = b""
            if content_length > 0:
                body_raw = await asyncio.wait_for(
                    reader.readexactly(content_length), timeout=self._timeout_s
                )

            try:
                response_body = json.loads(body_raw.decode()) if body_raw else {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                response_body = {"_raw": body_raw.decode(errors="replace")}

            return status_code, response_body
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _build_headers(self, method: str, path: str, body: bytes | None) -> list[str]:
        headers = [
            f"{method} {path} HTTP/1.1",
            "Connection: close",
        ]
        if body is not None:
            headers.append(f"Content-Length: {len(body)}")
            headers.append("Content-Type: application/json; charset=utf-8")
        if self._auth_header:
            headers.append(f"Authorization: {self._auth_header}")
        return headers

    @staticmethod
    def _parse_status(line: str) -> int:
        try:
            return int(line.split(" ", 2)[1])
        except (IndexError, ValueError):
            return 0


class OneCClient:
    def __init__(self, config: OneCConfig | None = None) -> None:
        self._config = config or OneCConfig()
        self._status = OneCSyncStatus()
        self._transport: _HttpTransport | None = None
        self._pending_sales: list[dict[str, Any]] = []
        if self._config.enabled:
            self._transport = AsyncioHttpTransport(
                base_url=self._config.base_url,
                timeout_s=self._config.timeout_s,
            )
            if self._config.username:
                self._transport.set_basic_auth(self._config.username, self._config.password)

    @property
    def config(self) -> OneCConfig:
        return self._config

    @property
    def status(self) -> OneCSyncStatus:
        return self._status

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    async def health_check(self) -> bool:
        if not self.enabled or self._transport is None:
            return False
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                status_code, _ = await self._transport.get("/ping")
                if status_code == 200:
                    self._status.connected = True
                    self._status.last_error = None
                    return True
            except Exception as exc:
                self._status.last_error = str(exc)
                _logger.warning("1c_health_check_failed attempt=%d error=%s", attempt, exc)
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BASE_BACKOFF_S * (2 ** (attempt - 1)))
        self._status.connected = False
        return False

    async def sync_inventory(self, products: list[dict[str, Any]]) -> bool:
        if not self.enabled or not self._config.import_inventory or self._transport is None:
            return False
        try:
            status_code, _ = await self._transport.post("/inventory", {"products": products})
            if status_code == 200:
                self._status.last_inventory_sync_at = _utc_now_iso()
                self._status.last_error = None
                return True
        except Exception as exc:
            self._status.last_error = str(exc)
            _logger.warning("1c_inventory_sync_failed error=%s", exc)
        return False

    async def export_sale(self, transaction: Transaction) -> bool:
        if not self.enabled or not self._config.export_sales or self._transport is None:
            self._status.pending_sales_count += 1
            return False
        payload = {
            "transaction_id": transaction.transaction_id.value,
            "product_id": transaction.product_id.value,
            "slot_id": transaction.slot_id.value,
            "price_minor_units": transaction.price.minor_units,
            "currency": transaction.price.currency.code,
            "accepted_minor_units": transaction.accepted_amount.minor_units,
            "change_due_minor_units": transaction.change_due.minor_units,
            "status": transaction.status.value,
            "completed_at": _utc_now_iso(),
        }
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                status_code, _ = await self._transport.post("/sales", {"sale": payload})
                if status_code in (200, 201):
                    self._status.last_sales_export_at = _utc_now_iso()
                    self._status.last_error = None
                    return True
            except Exception as exc:
                self._status.last_error = str(exc)
                _logger.warning("1c_sales_export_failed attempt=%d error=%s", attempt, exc)
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BASE_BACKOFF_S * (2 ** (attempt - 1)))
        self._status.pending_sales_count += 1
        self._pending_sales.append(payload)
        return False

    async def update_prices(self) -> list[dict[str, Any]]:
        if not self.enabled or not self._config.import_prices or self._transport is None:
            return []
        try:
            status_code, body = await self._transport.get("/prices")
            if status_code == 200:
                self._status.last_price_update_at = _utc_now_iso()
                self._status.last_error = None
                return body.get("items", [])
        except Exception as exc:
            self._status.last_error = str(exc)
            _logger.warning("1c_price_update_failed error=%s", exc)
        return []

    async def report_device_status(self, devices: list[dict[str, Any]]) -> bool:
        if not self.enabled or not self._config.report_device_status or self._transport is None:
            return False
        try:
            status_code, _ = await self._transport.post("/device-status", {"devices": devices})
            return status_code == 200
        except Exception as exc:
            self._status.last_error = str(exc)
            _logger.warning("1c_device_status_failed error=%s", exc)
            return False

    async def flush_pending_sales(self) -> int:
        if not self._pending_sales or self._transport is None:
            return 0
        sent = 0
        remaining: list[dict[str, Any]] = []
        for sale in self._pending_sales:
            try:
                status_code, _ = await self._transport.post("/sales", {"sale": sale})
                if status_code in (200, 201):
                    sent += 1
                else:
                    remaining.append(sale)
            except Exception:
                remaining.append(sale)
        self._pending_sales = remaining
        self._status.pending_sales_count = len(remaining)
        if sent:
            self._status.last_sales_export_at = _utc_now_iso()
        return sent
