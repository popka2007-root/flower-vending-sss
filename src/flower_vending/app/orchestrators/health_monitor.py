"""Health monitoring and machine sale blocking."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timezone

from flower_vending.app.event_bus import EventBus
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.devices.contracts import DeviceHealth, DeviceOperationalState
from flower_vending.devices.interfaces import DoorSensor, ManagedDevice, TemperatureSensor
from flower_vending.domain.entities import DeviceHealthSnapshot
from flower_vending.domain.events.machine_events import machine_event
from flower_vending.domain.value_objects import DeviceState

_DEVICE_HEALTH_TIMEOUT_S: float = 5.0


class HealthMonitor:
    def __init__(
        self,
        *,
        devices: Mapping[str, ManagedDevice],
        machine_status_service: MachineStatusService,
        event_bus: EventBus,
        door_sensor: DoorSensor | None = None,
        temperature_sensor: TemperatureSensor | None = None,
        critical_temperature_celsius: float = 8.0,
        device_health_timeout_s: float = _DEVICE_HEALTH_TIMEOUT_S,
    ) -> None:
        self._devices = devices
        self._machine_status_service = machine_status_service
        self._event_bus = event_bus
        self._door_sensor = door_sensor
        self._temperature_sensor = temperature_sensor
        self._critical_temperature_celsius = critical_temperature_celsius
        self._device_health_timeout_s = device_health_timeout_s
        self._snapshot = DeviceHealthSnapshot()

    @property
    def snapshot(self) -> DeviceHealthSnapshot:
        return self._snapshot

    async def _check_device_health(self, device: ManagedDevice) -> DeviceHealth:
        return await asyncio.wait_for(
            device.get_health(),
            timeout=self._device_health_timeout_s,
        )

    async def poll_once(self, correlation_id: str = "health-monitor") -> DeviceHealthSnapshot:
        """Execute a single health monitoring pass with timeouts."""
        faults: list[str] = []
        state_map: dict[str, DeviceState] = {}
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        # Phase 1: Check managed devices with strict timeout handling.
        for name, device in self._devices.items():
            try:
                # Wrap each health check in a timeout to prevent loop blocking.
                health = await self._check_device_health(device)
                state = DeviceState(health.state.value)
                state_map[name] = state
                if health.state in {
                    DeviceOperationalState.FAULT,
                    DeviceOperationalState.RECOVERY_PENDING,
                    DeviceOperationalState.OUT_OF_SERVICE,
                }:
                    faults.append(name)
            except asyncio.TimeoutError:
                # Handle device hangs by marking them as FAULT and recording a timeout.
                state_map[name] = DeviceState.FAULT
                faults.append(f"{name}_timeout")

        # Phase 2: Update machine status based on device health.
        for name in self._devices:
            key = f"device_fault:{name}"
            device_state = state_map.get(name, DeviceState.FAULT)
            if device_state in {
                DeviceState.FAULT,
                DeviceState.RECOVERY_PENDING,
                DeviceState.OUT_OF_SERVICE,
            }:
                self._machine_status_service.block_sales(key)
            else:
                self._machine_status_service.unblock_sales(key)

        # Phase 3: Update and publish health snapshot.
        self._snapshot = DeviceHealthSnapshot(
            validator_state=state_map.get("validator", DeviceState.UNKNOWN),
            change_dispenser_state=state_map.get("change_dispenser", DeviceState.UNKNOWN),
            motor_state=state_map.get("motor", DeviceState.UNKNOWN),
            cooling_state=state_map.get("cooling", DeviceState.UNKNOWN),
            window_state=state_map.get("window", DeviceState.UNKNOWN),
            temperature_sensor_state=state_map.get("temperature", DeviceState.UNKNOWN),
            door_sensor_state=state_map.get("door", DeviceState.UNKNOWN),
            inventory_sensor_state=state_map.get("inventory", DeviceState.UNKNOWN),
            watchdog_state=state_map.get("watchdog", DeviceState.UNKNOWN),
            last_heartbeat_at=now_iso,
            faults=faults,
        )
        if faults:
            await self._event_bus.publish(
                machine_event("machine_faulted", correlation_id=correlation_id, faults=faults)
            )

        # Phase 4: Handle auxiliary sensors with explicit timeout wrapping.
        if self._door_sensor is not None:
            try:
                door = await asyncio.wait_for(
                    self._door_sensor.read_service_door(),
                    timeout=self._device_health_timeout_s,
                )
                if door.is_open:
                    self._machine_status_service.block_sales("service_door_open")
                    await self._event_bus.publish(
                        machine_event("service_door_opened", correlation_id=correlation_id)
                    )
                else:
                    self._machine_status_service.unblock_sales("service_door_open")
                self._snapshot.door_sensor_state = DeviceState.READY
            except asyncio.TimeoutError:
                # Mark sensor fault and block sales if reading hangs.
                self._snapshot.door_sensor_state = DeviceState.FAULT
                if "door_sensor_timeout" not in self._snapshot.faults:
                    self._snapshot.faults.append("door_sensor_timeout")
                self._machine_status_service.block_sales("device_fault:door")

        if self._temperature_sensor is not None:
            try:
                reading = await asyncio.wait_for(
                    self._temperature_sensor.read_temperature(),
                    timeout=self._device_health_timeout_s,
                )
                if reading.celsius >= self._critical_temperature_celsius:
                    self._machine_status_service.block_sales("critical_temperature")
                    await self._event_bus.publish(
                        machine_event(
                            "critical_temperature_detected",
                            correlation_id=correlation_id,
                            celsius=reading.celsius,
                        )
                    )
                else:
                    self._machine_status_service.unblock_sales("critical_temperature")
                self._snapshot.temperature_sensor_state = DeviceState.READY
            except asyncio.TimeoutError:
                # Mark sensor fault and block sales if reading hangs.
                self._snapshot.temperature_sensor_state = DeviceState.FAULT
                if "temperature_sensor_timeout" not in self._snapshot.faults:
                    self._snapshot.faults.append("temperature_sensor_timeout")
                self._machine_status_service.block_sales("device_fault:temperature")

        return self._snapshot
