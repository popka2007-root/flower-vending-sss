"""Arduino/ESP32 cooling controller via RELAY2."""

from __future__ import annotations

from dataclasses import replace

from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceHealth,
    DeviceOperationalState,
    utc_now,
)
from flower_vending.devices.interfaces import CoolingController
from flower_vending.devices.arduino.transport import ArduinoSerialTransport


class ArduinoCoolingController(CoolingController):
    def __init__(
        self,
        transport: ArduinoSerialTransport,
        name: str = "arduino_cooling",
        *,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        self._transport = transport
        self._name = name
        self._policy = command_policy or DeviceCommandPolicy()
        self._started = False
        self._enabled = False
        self._target_celsius = 4.0
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
        try:
            await self._transport.command("COOL_OFF")
        except Exception:
            pass
        self._health = replace(
            self._health,
            state=DeviceOperationalState.DISABLED,
            last_heartbeat_at=utc_now(),
        )

    async def get_health(self) -> DeviceHealth:
        return self._health

    async def set_enabled(self, enabled: bool) -> None:
        if enabled:
            await self._transport.command("COOL_ON")
        else:
            await self._transport.command("COOL_OFF")
        self._enabled = enabled
        self._heartbeat()

    async def set_target_celsius(self, target_celsius: float) -> None:
        self._target_celsius = target_celsius
        self._heartbeat()

    def _heartbeat(self) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
            faults=self._health.faults,
            details={"enabled": self._enabled, "target_celsius": self._target_celsius},
        )
