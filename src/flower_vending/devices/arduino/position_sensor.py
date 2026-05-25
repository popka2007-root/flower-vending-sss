"""Arduino/ESP32 drum position sensor via AS5045 PWM (GPIO26)."""

from __future__ import annotations

from dataclasses import replace

from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceHealth,
    DeviceOperationalState,
    PositionReading,
    utc_now,
)
from flower_vending.devices.interfaces import PositionSensor
from flower_vending.devices.arduino.transport import ArduinoSerialTransport


class ArduinoPositionSensor(PositionSensor):
    def __init__(
        self,
        transport: ArduinoSerialTransport,
        name: str = "arduino_position",
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

    async def read_position(self) -> PositionReading:
        status = await self._transport.command_status()
        drum_str = status.get("drum", "0")
        try:
            drum_pos = int(drum_str)
        except (ValueError, TypeError):
            drum_pos = 0
        in_home = abs(drum_pos - self._home_pos) < 10 if self._home_pos >= 0 else False
        self._heartbeat(position=drum_pos)
        return PositionReading(
            sensor_name=self.name,
            position_id="drum",
            in_position=in_home,
            is_home=in_home,
        )

    async def calibrate_home(self) -> None:
        _ = await self._transport.command("ENC_CALIBRATE")
        self._home_pos = 0

    def _heartbeat(self, **details: object) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
            faults=self._health.faults,
            details=details,
        )

    _home_pos: int = -1
