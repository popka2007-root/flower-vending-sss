"""Arduino/ESP32 service door sensor via BUTTON pin."""

from __future__ import annotations

from dataclasses import replace

from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceHealth,
    DeviceOperationalState,
    DoorStatus,
    utc_now,
)
from flower_vending.devices.interfaces import DoorSensor
from flower_vending.devices.arduino.transport import ArduinoSerialTransport


class ArduinoDoorSensor(DoorSensor):
    def __init__(
        self,
        transport: ArduinoSerialTransport,
        name: str = "arduino_door_sensor",
        *,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        self._transport = transport
        self._name = name
        self._policy = command_policy or DeviceCommandPolicy()
        self._started = False
        self._health = DeviceHealth(name=name, state=DeviceOperationalState.UNKNOWN)

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        self._started = True
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

    async def read_service_door(self) -> DoorStatus:
        status = await self._transport.command_status()
        is_open = status.get("button", "OFF") == "ON"
        self._heartbeat(is_open=is_open)
        return DoorStatus(sensor_name=self.name, is_open=is_open)

    def _heartbeat(self, **details: object) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
            faults=self._health.faults,
            details=details,
        )
