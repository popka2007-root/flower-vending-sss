"""Arduino/ESP32 delivery window controller."""

from __future__ import annotations

from dataclasses import replace

from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceHealth,
    DeviceOperationalState,
    WindowPosition,
    WindowStatus,
    utc_now,
)
from flower_vending.devices.interfaces import WindowController
from flower_vending.devices.arduino.transport import ArduinoSerialTransport


class ArduinoWindowController(WindowController):
    def __init__(
        self,
        transport: ArduinoSerialTransport,
        name: str = "arduino_window",
        *,
        pulse_ms: int = 700,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        self._transport = transport
        self._name = name
        self._pulse_ms = pulse_ms
        self._policy = command_policy or DeviceCommandPolicy()
        self._started = False
        self._position = WindowPosition.CLOSED
        self._health = DeviceHealth(name=name, state=DeviceOperationalState.UNKNOWN)

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        self._started = True
        self._position = WindowPosition.CLOSED
        self._health = replace(
            self._health,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
        )

    async def stop(self) -> None:
        self._started = False
        self._health = replace(
            self._health,
            state=DeviceOperationalState.DISABLED,
            last_heartbeat_at=utc_now(),
        )

    async def get_health(self) -> DeviceHealth:
        return self._health

    async def open_window(self, correlation_id: str | None = None) -> None:
        await self._transport.command("DOOR_OPEN")
        self._position = WindowPosition.OPEN
        self._heartbeat()

    async def close_window(self, correlation_id: str | None = None) -> None:
        await self._transport.command("DOOR_CLOSE")
        self._position = WindowPosition.CLOSED
        self._heartbeat()

    async def get_window_status(self) -> WindowStatus:
        try:
            status = await self._transport.command_status()
            pos = status.get("door", self._position.value)
            self._position = (
                WindowPosition(pos.upper()) if pos.upper() in ("OPEN", "CLOSED") else self._position
            )
        except Exception:
            pass
        return WindowStatus(
            controller_name=self.name,
            position=self._position,
            locked=not self._started,
        )

    def _heartbeat(self) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
            faults=self._health.faults,
            details={"position": self._position.value},
        )
