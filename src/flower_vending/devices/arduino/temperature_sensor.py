"""Arduino/ESP32 temperature sensor via DS18B20."""

from __future__ import annotations

from dataclasses import replace

from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceHealth,
    DeviceOperationalState,
    TemperatureReading,
    utc_now,
)
from flower_vending.devices.interfaces import TemperatureSensor
from flower_vending.devices.arduino.transport import ArduinoSerialTransport


class ArduinoTemperatureSensor(TemperatureSensor):
    def __init__(
        self,
        transport: ArduinoSerialTransport,
        name: str = "arduino_temp",
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

    async def read_temperature(self) -> TemperatureReading:
        resp = await self._transport.command("TEMP")
        celsius = 25.0
        try:
            for part in resp.replace("OK ", "").split():
                if part.startswith("TEMP="):
                    celsius = float(part.split("=")[1])
        except (ValueError, IndexError):
            pass
        self._heartbeat(celsius=celsius)
        return TemperatureReading(sensor_name=self.name, celsius=celsius)

    def _heartbeat(self, **details: object) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
            faults=self._health.faults,
            details=details,
        )
