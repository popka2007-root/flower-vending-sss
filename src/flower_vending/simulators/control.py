"""Simulator control plane exposed to UI and CLI layers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Final

from flower_vending.app import ApplicationCore
from flower_vending.domain.events import DomainEvent
from flower_vending.domain.events.machine_events import machine_event
from flower_vending.simulators.devices import (
    MockBillValidator,
    MockChangeDispenser,
    MockDoorSensor,
    MockInventorySensor,
    MockMotorController,
    MockTemperatureSensor,
    MockWatchdogAdapter,
    MockWindowController,
)
from flower_vending.simulators.faults import SimulatorFaultCode


SIMULATOR_ACTIONS: Final[tuple[str, ...]] = (
    "open_service_door",
    "close_service_door",
    "raise_temperature_critical",
    "restore_temperature_nominal",
    "inject_validator_unavailable",
    "inject_bill_rejected",
    "inject_bill_jam",
    "inject_payout_unavailable",
    "inject_partial_payout",
    "inject_motor_fault",
    "inject_window_fault",
    "inject_inventory_mismatch",
    "restore_inventory_match",
    "clear_simulator_faults",
    "force_pickup_timeout_now",
    "inject_power_loss_during_motion",
)


@dataclass(frozen=True, slots=True)
class EventLogEntry:
    timestamp: str
    event_type: str
    correlation_id: str
    transaction_id: str | None
    summary: str


class RecentEventStore:
    def __init__(self, limit: int = 100) -> None:
        self._entries: deque[EventLogEntry] = deque(maxlen=limit)

    async def handle(self, event: DomainEvent) -> None:
        self._entries.append(
            EventLogEntry(
                timestamp=event.occurred_at.isoformat(),
                event_type=event.event_type,
                correlation_id=event.correlation_id,
                transaction_id=event.transaction_id,
                summary=self._build_summary(event),
            )
        )

    def snapshot(self) -> tuple[EventLogEntry, ...]:
        return tuple(self._entries)

    def _build_summary(self, event: DomainEvent) -> str:
        if event.payload:
            parts = [f"{key}={value}" for key, value in sorted(event.payload.items())]
            return ", ".join(parts)
        return event.event_type


class SimulatorControlService:
    def __init__(
        self,
        *,
        core: ApplicationCore,
        validator: MockBillValidator,
        change_dispenser: MockChangeDispenser,
        motor_controller: MockMotorController,
        window_controller: MockWindowController,
        temperature_sensor: MockTemperatureSensor,
        door_sensor: MockDoorSensor,
        inventory_sensor: MockInventorySensor,
        watchdog: MockWatchdogAdapter,
        quick_insert_denominations: tuple[int, ...],
        default_slot_id: str,
    ) -> None:
        self._core = core
        self._validator = validator
        self._change_dispenser = change_dispenser
        self._motor_controller = motor_controller
        self._window_controller = window_controller
        self._temperature_sensor = temperature_sensor
        self._door_sensor = door_sensor
        self._inventory_sensor = inventory_sensor
        self._watchdog = watchdog
        self._quick_insert_denominations = quick_insert_denominations
        self._default_slot_id = default_slot_id

    def quick_insert_denominations(self) -> tuple[int, ...]:
        return self._quick_insert_denominations

    def available_actions(self) -> tuple[str, ...]:
        return SIMULATOR_ACTIONS

    async def insert_bill(self, bill_minor_units: int, *, correlation_id: str) -> None:
        await self._validator.simulate_insert_bill(
            bill_minor_units=bill_minor_units,
            correlation_id=correlation_id,
        )
        await self._core.event_bus.publish(
            machine_event(
                "simulator_bill_inserted",
                correlation_id=correlation_id,
                bill_minor_units=bill_minor_units,
            )
        )

    async def execute_action(self, action_id: str, *, correlation_id: str) -> None:
        if action_id == "open_service_door":
            self._door_sensor.set_open(True)
            await self._poll_health(correlation_id)
            return
        if action_id == "close_service_door":
            self._door_sensor.set_open(False)
            await self._poll_health(correlation_id)
            return
        if action_id == "raise_temperature_critical":
            self._temperature_sensor.set_celsius(9.5)
            await self._poll_health(correlation_id)
            return
        if action_id == "restore_temperature_nominal":
            self._temperature_sensor.set_celsius(4.0)
            await self._poll_health(correlation_id)
            return
        if action_id == "inject_validator_unavailable":
            self._validator.inject_fault(
                SimulatorFaultCode.VALIDATOR_UNAVAILABLE,
                message="simulator validator unavailable",
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "inject_bill_rejected":
            self._validator.inject_fault(
                SimulatorFaultCode.BILL_REJECTED,
                message="simulator bill rejected",
                critical=False,
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "inject_bill_jam":
            self._validator.inject_fault(
                SimulatorFaultCode.BILL_JAM,
                message="simulator bill jam",
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "inject_payout_unavailable":
            self._change_dispenser.inject_fault(
                SimulatorFaultCode.PAYOUT_UNAVAILABLE,
                message="simulator payout unavailable",
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "inject_partial_payout":
            self._change_dispenser.inject_fault(
                SimulatorFaultCode.PARTIAL_PAYOUT,
                message="simulator partial payout",
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "inject_motor_fault":
            self._motor_controller.inject_fault(
                SimulatorFaultCode.MOTOR_FAULT,
                message="simulator motor fault",
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "inject_window_fault":
            self._window_controller.inject_fault(
                SimulatorFaultCode.WINDOW_FAULT,
                message="simulator delivery window fault",
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "inject_inventory_mismatch":
            self._inventory_sensor.set_slot_presence(
                self._default_slot_id,
                has_product=False,
                confidence=1.0,
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "restore_inventory_match":
            self._inventory_sensor.set_slot_presence(
                self._default_slot_id,
                has_product=True,
                confidence=1.0,
            )
            await self._announce_action(action_id, correlation_id)
            return
        if action_id == "clear_simulator_faults":
            for device in (
                self._validator,
                self._change_dispenser,
                self._motor_controller,
                self._window_controller,
                self._watchdog,
            ):
                device.clear_faults()
            await self._announce_action(action_id, correlation_id)
            await self._poll_health(correlation_id)
            return
        if action_id == "force_pickup_timeout_now":
            transaction_id = await self._core.pickup_timeout_coordinator.force_timeout_now(
                correlation_id=correlation_id,
            )
            await self._announce_action(action_id, correlation_id, transaction_id=transaction_id)
            return
        if action_id == "inject_power_loss_during_motion":
            self._motor_controller.inject_fault(
                SimulatorFaultCode.POWER_LOSS_DURING_MOTION,
                message="simulator power loss during motor motion",
            )
            await self._announce_action(action_id, correlation_id)
            return
        raise KeyError(f"unknown simulator action: {action_id}")

    async def _poll_health(self, correlation_id: str) -> None:
        await self._announce_action("health_refresh_requested", correlation_id)
        await self._core.health_monitor.poll_once(correlation_id=correlation_id)

    async def _announce_action(
        self,
        action_id: str,
        correlation_id: str,
        **payload: object,
    ) -> None:
        await self._core.event_bus.publish(
            machine_event(
                "simulator_action_applied",
                correlation_id=correlation_id,
                action_id=action_id,
                **payload,
            )
        )
