"""Bootstrap wiring for the Phase 5 application core."""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Coroutine, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from flower_vending.app.command_bus import CommandBus
from flower_vending.app.event_bus import EventBus
from flower_vending.app.fsm import MachineState, StateMachineEngine
from flower_vending.app.journal import ApplicationJournal, NoopApplicationJournal
from flower_vending.app.orchestrators import (
    DisplayRotationController,
    HealthMonitor,
    IdleTimeoutCoordinator,
    PaymentCoordinator,
    PickupTimeoutCoordinator,
    RecoveryManager,
    ServiceModeCoordinator,
    TransactionCoordinator,
    VendingController,
)
from flower_vending.app.services import InventoryService, MachineStatusService
from flower_vending.devices.contracts import BillValidatorEvent
from flower_vending.devices.interfaces import (
    BillValidator,
    ChangeDispenser,
    DoorSensor,
    InventorySensor,
    ManagedDevice,
    MotorController,
    TemperatureSensor,
    WatchdogAdapter,
    WindowController,
)
from flower_vending.domain.aggregates import MachineRuntimeAggregate
from flower_vending.domain.commands.purchase_commands import (
    AcceptCash,
    CancelPurchase,
    ConfirmPickup,
    StartPurchase,
)
from flower_vending.domain.commands.recovery_commands import RecoverInterruptedTransaction
from flower_vending.domain.commands.service_commands import (
    EnterServiceMode,
    LockPurchaseButton,
    ToggleProductCommand,
)
from flower_vending.domain.entities import MoneyInventory
from flower_vending.payments.change_manager import ChangeManager


@dataclass(slots=True)
class ApplicationCore:
    validator: BillValidator
    command_bus: CommandBus
    event_bus: EventBus
    fsm: StateMachineEngine
    inventory_service: InventoryService
    machine_status_service: MachineStatusService
    transaction_coordinator: TransactionCoordinator
    journal: ApplicationJournal
    payment_coordinator: PaymentCoordinator
    vending_controller: VendingController
    recovery_manager: RecoveryManager
    pickup_timeout_coordinator: PickupTimeoutCoordinator
    service_mode_coordinator: ServiceModeCoordinator
    health_monitor: HealthMonitor
    idle_timeout_coordinator: IdleTimeoutCoordinator
    display_rotation_controller: DisplayRotationController | None = None
    watchdog: WatchdogAdapter | None = None
    health_poll_interval_s: float = 0.5
    display_rotation_poll_interval_s: float = 1.0
    validator_event_timeout_s: float = 0.05
    watchdog_timeout_s: float = 30.0
    pickup_timeout_poll_interval_s: float = 0.25
    _runtime_stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _runtime_tasks: list[asyncio.Task[None]] = field(default_factory=list, init=False)
    _runtime_failures: list[BaseException] = field(default_factory=list, init=False)

    async def process_validator_event(self, event: BillValidatorEvent) -> None:
        await self.payment_coordinator.process_validator_event(event)

    async def start_runtime(self) -> None:
        """Start application-owned background supervision loops."""
        if self._runtime_tasks:
            return
        self._runtime_stop.clear()
        self._runtime_failures.clear()
        await self.health_monitor.poll_once(correlation_id="startup-health")
        if self.watchdog is not None:
            await self.watchdog.arm(self.watchdog_timeout_s)
        self._spawn_runtime_task(self._validator_event_loop(), "validator-events")
        self._spawn_runtime_task(self._health_monitor_loop(), "health-monitor")
        self._spawn_runtime_task(self._pickup_timeout_loop(), "pickup-timeout")
        self._spawn_runtime_task(self._idle_timeout_loop(), "idle-timeout")
        if self.display_rotation_controller is not None:
            self._spawn_runtime_task(self._display_rotation_loop(), "display-rotation")

    async def stop_runtime(self) -> None:
        self._runtime_stop.set()

        def _tasks_by_name(name: str) -> list[asyncio.Task[None]]:
            return [t for t in self._runtime_tasks if t.get_name() == f"flower-vending-{name}"]

        async def _cancel_group(name: str) -> None:
            tasks = _tasks_by_name(name)
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        await _cancel_group("health-monitor")
        await _cancel_group("validator-events")
        await _cancel_group("pickup-timeout")
        await _cancel_group("idle-timeout")
        await _cancel_group("display-rotation")

        self._runtime_tasks.clear()
        if self.watchdog is not None:
            with suppress(Exception):
                await self.watchdog.disarm()

    def raise_runtime_failure(self) -> None:
        if self._runtime_failures:
            raise self._runtime_failures.pop(0)

    def _spawn_runtime_task(self, coroutine: Coroutine[Any, Any, None], name: str) -> None:
        task = asyncio.create_task(coroutine, name=f"flower-vending-{name}")
        task.add_done_callback(self._capture_runtime_failure)
        self._runtime_tasks.append(task)

    def _capture_runtime_failure(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None:
            self._runtime_failures.append(failure)

    async def _validator_event_loop(self) -> None:
        while not self._runtime_stop.is_set():
            event = await self.validator.read_event(timeout_s=self.validator_event_timeout_s)
            if event is None:
                continue
            await self.process_validator_event(event)

    async def _health_monitor_loop(self) -> None:
        while not self._runtime_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._runtime_stop.wait(),
                    timeout=self.health_poll_interval_s,
                )
                break
            except asyncio.TimeoutError:
                pass
            await self.health_monitor.poll_once()
            if self.watchdog is not None:
                await self.watchdog.kick()

    async def _pickup_timeout_loop(self) -> None:
        await self.pickup_timeout_coordinator.poll_once(correlation_id="startup-pickup-timeout")
        while not self._runtime_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._runtime_stop.wait(),
                    timeout=self.pickup_timeout_poll_interval_s,
                )
                break
            except asyncio.TimeoutError:
                pass
            await self.pickup_timeout_coordinator.poll_once()

    async def _idle_timeout_loop(self) -> None:
        poll_interval = max(self.idle_timeout_coordinator.timeout_s / 10.0, 1.0)
        while not self._runtime_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._runtime_stop.wait(),
                    timeout=poll_interval,
                )
                break
            except asyncio.TimeoutError:
                pass
            await self.idle_timeout_coordinator.poll_once()

    async def _display_rotation_loop(self) -> None:
        if self.display_rotation_controller is None:
            return
        while not self._runtime_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._runtime_stop.wait(),
                    timeout=self.display_rotation_poll_interval_s,
                )
                break
            except asyncio.TimeoutError:
                pass
            await self.display_rotation_controller.poll_once()


def _setup_services(
    money_inventory: MoneyInventory,
    change_dispenser: ChangeDispenser,
    accepted_bill_denominations: tuple[int, ...],
    initial_state: MachineState,
) -> tuple[ChangeManager, MachineStatusService]:
    change_manager = ChangeManager(
        inventory=money_inventory,
        change_dispenser=change_dispenser,
        accepted_bill_denominations=accepted_bill_denominations,
    )
    machine_status_service = MachineStatusService(
        MachineRuntimeAggregate(), change_manager=change_manager
    )
    machine_status_service.set_machine_state(initial_state)
    return change_manager, machine_status_service


def _setup_journal(journal: ApplicationJournal | None) -> ApplicationJournal:
    if journal is None:
        warnings.warn(
            "No ApplicationJournal provided — using NoopApplicationJournal. "
            "Intent/outcome records will not be persisted.",
            stacklevel=2,
        )
    return journal or NoopApplicationJournal()


def _create_orchestrators(
    validator: BillValidator,
    change_manager: ChangeManager,
    event_bus: EventBus,
    fsm: StateMachineEngine,
    machine_status_service: MachineStatusService,
    application_journal: ApplicationJournal,
    inventory_service: InventoryService,
    motor_controller: MotorController,
    window_controller: WindowController,
    inventory_sensor: InventorySensor | None,
    pickup_timeout_s: float,
    service_pin: str,
    devices: Mapping[str, ManagedDevice],
    door_sensor: DoorSensor | None,
    temperature_sensor: TemperatureSensor | None,
    critical_temperature_celsius: float,
    idle_timeout_s: float,
) -> tuple[
    TransactionCoordinator,
    PaymentCoordinator,
    VendingController,
    RecoveryManager,
    PickupTimeoutCoordinator,
    ServiceModeCoordinator,
    HealthMonitor,
    IdleTimeoutCoordinator,
    DisplayRotationController,
]:
    transaction_coordinator = TransactionCoordinator()
    payment_coordinator = PaymentCoordinator(
        validator=validator,
        change_manager=change_manager,
        transaction_coordinator=transaction_coordinator,
        event_bus=event_bus,
        fsm=fsm,
        machine_status_service=machine_status_service,
        journal=application_journal,
    )
    vending_controller = VendingController(
        inventory_service=inventory_service,
        payment_coordinator=payment_coordinator,
        transaction_coordinator=transaction_coordinator,
        motor_controller=motor_controller,
        window_controller=window_controller,
        inventory_sensor=inventory_sensor,
        event_bus=event_bus,
        fsm=fsm,
        machine_status_service=machine_status_service,
        journal=application_journal,
    )
    recovery_manager = RecoveryManager(
        transaction_coordinator=transaction_coordinator,
        event_bus=event_bus,
        fsm=fsm,
        machine_status_service=machine_status_service,
        journal=application_journal,
    )
    pickup_timeout_coordinator = PickupTimeoutCoordinator(
        transaction_coordinator=transaction_coordinator,
        window_controller=window_controller,
        event_bus=event_bus,
        fsm=fsm,
        machine_status_service=machine_status_service,
        pickup_timeout_s=pickup_timeout_s,
        journal=application_journal,
    )
    service_mode_coordinator = ServiceModeCoordinator(
        event_bus=event_bus,
        fsm=fsm,
        machine_status_service=machine_status_service,
        service_pin=service_pin,
    )
    health_monitor = HealthMonitor(
        devices=devices,
        machine_status_service=machine_status_service,
        event_bus=event_bus,
        door_sensor=door_sensor,
        temperature_sensor=temperature_sensor,
        critical_temperature_celsius=critical_temperature_celsius,
    )
    idle_timeout_coordinator = IdleTimeoutCoordinator(
        payment_coordinator=payment_coordinator,
        transaction_coordinator=transaction_coordinator,
        event_bus=event_bus,
        fsm=fsm,
        machine_status_service=machine_status_service,
        idle_timeout_s=idle_timeout_s,
        journal=application_journal,
    )
    display_rotation_controller = DisplayRotationController(
        motor_controller=motor_controller,
        fsm=fsm,
        machine_status_service=machine_status_service,
    )

    return (
        transaction_coordinator,
        payment_coordinator,
        vending_controller,
        recovery_manager,
        pickup_timeout_coordinator,
        service_mode_coordinator,
        health_monitor,
        idle_timeout_coordinator,
        display_rotation_controller,
    )


def _register_bus_handlers(
    command_bus: CommandBus,
    event_bus: EventBus,
    vending_controller: VendingController,
    recovery_manager: RecoveryManager,
    service_mode_coordinator: ServiceModeCoordinator,
    pickup_timeout_coordinator: PickupTimeoutCoordinator,
) -> None:
    command_bus.register_handler(StartPurchase, vending_controller.start_purchase)
    command_bus.register_handler(AcceptCash, vending_controller.accept_cash)
    command_bus.register_handler(CancelPurchase, vending_controller.cancel_purchase)
    command_bus.register_handler(ConfirmPickup, vending_controller.confirm_pickup)
    command_bus.register_handler(ToggleProductCommand, vending_controller.handle_toggle_product)
    command_bus.register_handler(
        RecoverInterruptedTransaction,
        lambda command: recovery_manager.recover_transaction(
            command.transaction_id, command.correlation_id
        ),
    )
    command_bus.register_handler(EnterServiceMode, service_mode_coordinator.enter_service_mode)
    command_bus.register_handler(LockPurchaseButton, service_mode_coordinator.lock_purchase_button)

    event_bus.subscribe_critical("vend_authorized", vending_controller.handle_vend_authorized)
    event_bus.subscribe_best_effort(
        "delivery_window_opened",
        pickup_timeout_coordinator.handle_delivery_window_opened,
    )
    event_bus.subscribe_best_effort(
        "pickup_confirmed", pickup_timeout_coordinator.handle_pickup_finished
    )
    event_bus.subscribe_best_effort(
        "transaction_completed",
        pickup_timeout_coordinator.handle_pickup_finished,
    )
    event_bus.subscribe_best_effort(
        "transaction_cancelled",
        pickup_timeout_coordinator.handle_pickup_finished,
    )


def build_application_core(
    *,
    validator: BillValidator,
    change_dispenser: ChangeDispenser,
    motor_controller: MotorController,
    window_controller: WindowController,
    inventory_service: InventoryService,
    money_inventory: MoneyInventory,
    devices: Mapping[str, ManagedDevice],
    accepted_bill_denominations: tuple[int, ...] = (),
    door_sensor: DoorSensor | None = None,
    temperature_sensor: TemperatureSensor | None = None,
    inventory_sensor: InventorySensor | None = None,
    initial_state: MachineState = MachineState.IDLE,
    critical_temperature_celsius: float = 8.0,
    health_poll_interval_s: float = 0.5,
    validator_event_timeout_s: float = 0.05,
    watchdog_timeout_s: float = 30.0,
    pickup_timeout_s: float = 60.0,
    journal: ApplicationJournal | None = None,
    service_pin: str = "0000",
    idle_timeout_s: float = 120.0,
) -> ApplicationCore:
    event_bus = EventBus()
    command_bus = CommandBus()
    fsm = StateMachineEngine(initial_state=initial_state)

    change_manager, machine_status_service = _setup_services(
        money_inventory=money_inventory,
        change_dispenser=change_dispenser,
        accepted_bill_denominations=accepted_bill_denominations,
        initial_state=initial_state,
    )

    application_journal = _setup_journal(journal)

    (
        transaction_coordinator,
        payment_coordinator,
        vending_controller,
        recovery_manager,
        pickup_timeout_coordinator,
        service_mode_coordinator,
        health_monitor,
        idle_timeout_coordinator,
        display_rotation_controller,
    ) = _create_orchestrators(
        validator=validator,
        change_manager=change_manager,
        event_bus=event_bus,
        fsm=fsm,
        machine_status_service=machine_status_service,
        application_journal=application_journal,
        inventory_service=inventory_service,
        motor_controller=motor_controller,
        window_controller=window_controller,
        inventory_sensor=inventory_sensor,
        pickup_timeout_s=pickup_timeout_s,
        service_pin=service_pin,
        devices=devices,
        door_sensor=door_sensor,
        temperature_sensor=temperature_sensor,
        critical_temperature_celsius=critical_temperature_celsius,
        idle_timeout_s=idle_timeout_s,
    )

    watchdog_device = devices.get("watchdog")
    watchdog = watchdog_device if isinstance(watchdog_device, WatchdogAdapter) else None

    _register_bus_handlers(
        command_bus=command_bus,
        event_bus=event_bus,
        vending_controller=vending_controller,
        recovery_manager=recovery_manager,
        service_mode_coordinator=service_mode_coordinator,
        pickup_timeout_coordinator=pickup_timeout_coordinator,
    )

    return ApplicationCore(
        validator=validator,
        command_bus=command_bus,
        event_bus=event_bus,
        fsm=fsm,
        inventory_service=inventory_service,
        machine_status_service=machine_status_service,
        transaction_coordinator=transaction_coordinator,
        journal=application_journal,
        payment_coordinator=payment_coordinator,
        vending_controller=vending_controller,
        recovery_manager=recovery_manager,
        pickup_timeout_coordinator=pickup_timeout_coordinator,
        service_mode_coordinator=service_mode_coordinator,
        health_monitor=health_monitor,
        idle_timeout_coordinator=idle_timeout_coordinator,
        display_rotation_controller=display_rotation_controller,
        watchdog=watchdog,
        health_poll_interval_s=health_poll_interval_s,
        validator_event_timeout_s=validator_event_timeout_s,
        watchdog_timeout_s=watchdog_timeout_s,
        pickup_timeout_poll_interval_s=min(max(pickup_timeout_s / 10.0, 0.05), 0.25),
    )
