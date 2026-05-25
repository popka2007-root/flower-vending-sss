"""Arduino/ESP32 drum motor controller with encoder positioning."""

from __future__ import annotations

from dataclasses import replace

from flower_vending.devices.contracts import (
    DeviceCommandPolicy,
    DeviceHealth,
    DeviceOperationalState,
    utc_now,
)
from flower_vending.devices.interfaces import MotorController
from flower_vending.devices.arduino.transport import ArduinoSerialTransport


class ArduinoMotorController(MotorController):
    def __init__(
        self,
        transport: ArduinoSerialTransport,
        name: str = "arduino_motor",
        *,
        vend_pulse_ms: int = 700,
        command_policy: DeviceCommandPolicy | None = None,
    ) -> None:
        self._transport = transport
        self._name = name
        self._vend_pulse_ms = vend_pulse_ms
        self._policy = command_policy or DeviceCommandPolicy()
        self._started = False
        self._health = DeviceHealth(name=name, state=DeviceOperationalState.UNKNOWN)

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        self._started = True
        try:
            await self._transport.command("MOTOR_OFF")
        except Exception:
            pass
        self._health = replace(
            self._health,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
        )

    async def stop(self) -> None:
        self._started = False
        try:
            await self._transport.command("ALL_OFF")
        except Exception:
            pass
        self._health = replace(
            self._health,
            state=DeviceOperationalState.DISABLED,
            last_heartbeat_at=utc_now(),
        )

    async def get_health(self) -> DeviceHealth:
        return self._health

    async def home(self, correlation_id: str | None = None) -> None:
        await self._transport.command("HOME")
        self._heartbeat(action="home")

    async def vend_slot(self, slot_id: str, correlation_id: str | None = None) -> None:
        slot_num = self._slot_to_number(slot_id)
        await self._transport.command(f"VEND_SLOT {slot_num}")
        self._heartbeat(last_slot=slot_id)

    async def start_motion(self) -> None:
        await self._transport.command("MOTOR_ON")
        self._heartbeat(action="start")

    async def stop_motion(self) -> None:
        await self._transport.command("MOTOR_OFF")
        self._heartbeat(action="stop")

    def _heartbeat(self, **details: object) -> None:
        self._health = DeviceHealth(
            name=self.name,
            state=DeviceOperationalState.READY,
            last_heartbeat_at=utc_now(),
            faults=self._health.faults,
            details=details,
        )

    def _slot_to_number(self, slot_id: str) -> int:
        mapping = {
            "A1": 1,
            "A2": 2,
            "B1": 3,
            "B2": 4,
            "C1": 5,
            "C2": 6,
        }
        return mapping.get(slot_id.upper(), 1)
