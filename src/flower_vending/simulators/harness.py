"""Headless simulator harness for deterministic vending scenarios."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from flower_vending.app import ApplicationCore, build_application_core
from flower_vending.app.journal import ApplicationJournal
from flower_vending.domain.commands.purchase_commands import AcceptCash, ConfirmPickup, StartPurchase
from flower_vending.domain.entities import MoneyInventory, Product, Slot
from flower_vending.domain.value_objects import Amount, Currency, ProductId, SlotId
from flower_vending.app.services import InventoryService
from flower_vending.devices.interfaces import ManagedDevice
from flower_vending.infrastructure.persistence.journal import SQLiteTransactionJournal
from flower_vending.infrastructure.persistence.sqlite import SQLiteDatabase, ensure_sqlite_schema
from flower_vending.simulators.devices import (
    MockBillValidator,
    MockChangeDispenser,
    MockCoolingController,
    MockDoorSensor,
    MockInventorySensor,
    MockMotorController,
    MockPositionSensor,
    MockTemperatureSensor,
    MockWatchdogAdapter,
    MockWindowController,
)
from flower_vending.simulators.scenario_result import EventRecorder, ScenarioResult


@dataclass(slots=True)
class SimulationHarness:
    core: ApplicationCore
    validator: MockBillValidator
    change_dispenser: MockChangeDispenser
    motor_controller: MockMotorController
    cooling_controller: MockCoolingController
    window_controller: MockWindowController
    temperature_sensor: MockTemperatureSensor
    door_sensor: MockDoorSensor
    inventory_sensor: MockInventorySensor
    position_sensor: MockPositionSensor
    watchdog: MockWatchdogAdapter
    money_inventory: MoneyInventory
    recorder: EventRecorder
    product_id: str
    slot_id: str
    _database: SQLiteDatabase | None = field(default=None, repr=False)

    @classmethod
    def build(
        cls,
        *,
        product_id: str = "rose_red",
        slot_id: str = "A1",
        price_minor_units: int = 500,
        currency_code: str = "RUB",
        slot_quantity: int = 1,
        change_inventory: dict[int, int] | None = None,
        accepted_bill_denominations: tuple[int, ...] = (500, 1000),
        inventory_presence: bool = True,
        inventory_confidence: float = 1.0,
        temperature_celsius: float = 4.0,
        service_door_open: bool = False,
        pickup_timeout_s: float = 60.0,
        journal: ApplicationJournal | None = None,
    ) -> "SimulationHarness":
        inventory_service = InventoryService()
        inventory_service.register_product(
            Product(
                product_id=ProductId(product_id),
                name=product_id,
                display_name=product_id.replace("_", " ").title(),
                price=Amount(price_minor_units, Currency(currency_code)),
                category="flowers",
            )
        )
        inventory_service.register_slot(
            Slot(
                slot_id=SlotId(slot_id),
                product_id=ProductId(product_id),
                capacity=max(1, slot_quantity),
                quantity=slot_quantity,
            )
        )

        money_inventory = MoneyInventory(
            currency=Currency(currency_code),
            accounting_counts_by_denomination=dict(change_inventory or {100: 10, 50: 10}),
        )

        validator = MockBillValidator(supported_bill_values=accepted_bill_denominations)
        change_dispenser = MockChangeDispenser(inventory=dict(money_inventory.accounting_counts_by_denomination))
        motor_controller = MockMotorController()
        cooling_controller = MockCoolingController()
        window_controller = MockWindowController()
        temperature_sensor = MockTemperatureSensor(celsius=temperature_celsius)
        door_sensor = MockDoorSensor(is_open=service_door_open)
        inventory_sensor = MockInventorySensor(slot_states={slot_id: (inventory_presence, inventory_confidence)})
        position_sensor = MockPositionSensor()
        watchdog = MockWatchdogAdapter()

        devices: dict[str, ManagedDevice] = {
            "validator": validator,
            "change_dispenser": change_dispenser,
            "motor": motor_controller,
            "cooling": cooling_controller,
            "window": window_controller,
            "temperature": temperature_sensor,
            "door": door_sensor,
            "inventory": inventory_sensor,
            "watchdog": watchdog,
        }

        if journal is None:
            tmp_dir = Path(tempfile.mkdtemp(prefix="flower_vending_harness_"))
            db_path = tmp_dir / "harness_journal.db"
            database = SQLiteDatabase(db_path, enable_wal=False, synchronous="NORMAL")
            ensure_sqlite_schema(database)
            journal = SQLiteTransactionJournal(database)
        else:
            database = None

        core = build_application_core(
            validator=validator,
            change_dispenser=change_dispenser,
            motor_controller=motor_controller,
            window_controller=window_controller,
            inventory_service=inventory_service,
            money_inventory=money_inventory,
            devices=devices,
            accepted_bill_denominations=accepted_bill_denominations,
            door_sensor=door_sensor,
            temperature_sensor=temperature_sensor,
            inventory_sensor=inventory_sensor,
            pickup_timeout_s=pickup_timeout_s,
            journal=journal,
        )
        recorder = EventRecorder()
        core.event_bus.subscribe_best_effort("*", recorder.handle)

        return cls(
            core=core,
            validator=validator,
            change_dispenser=change_dispenser,
            motor_controller=motor_controller,
            cooling_controller=cooling_controller,
            window_controller=window_controller,
            temperature_sensor=temperature_sensor,
            door_sensor=door_sensor,
            inventory_sensor=inventory_sensor,
            position_sensor=position_sensor,
            watchdog=watchdog,
            money_inventory=money_inventory,
            recorder=recorder,
            product_id=product_id,
            slot_id=slot_id,
            _database=database,
        )

    async def start(self) -> None:
        for device in self._all_devices():
            await device.start()
        await self.core.start_runtime()

    async def stop(self) -> None:
        await self.core.stop_runtime()
        for device in reversed(self._all_devices()):
            await device.stop()
        self._close_journal_database()

    def _close_journal_database(self) -> None:
        if self._database is None:
            return
        try:
            self._database.close()
        except Exception:
            pass
        db_path = Path(self._database.path)
        tmp_dir = db_path.parent
        if tmp_dir.name.startswith("flower_vending_harness_"):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def poll_health(self) -> None:
        await self.core.health_monitor.poll_once()

    async def start_purchase(self, *, correlation_id: str = "scenario") -> str:
        return await self.core.command_bus.dispatch(
            StartPurchase(
                correlation_id=correlation_id,
                product_id=self.product_id,
                slot_id=self.slot_id,
                price_minor_units=self._price_minor_units(),
            )
        )

    async def accept_cash(self, transaction_id: str, *, correlation_id: str = "scenario") -> str:
        return await self.core.command_bus.dispatch(
            AcceptCash(correlation_id=correlation_id, transaction_id=transaction_id)
        )

    async def insert_bill(
        self,
        bill_minor_units: int,
        *,
        correlation_id: str = "scenario",
        raise_on_error: bool = True,
    ) -> None:
        await self.validator.simulate_insert_bill(
            bill_minor_units=bill_minor_units,
            correlation_id=correlation_id,
        )
        try:
            await self.wait_for_runtime_processing()
        except Exception:
            if raise_on_error:
                raise

    async def confirm_pickup(self, transaction_id: str, *, correlation_id: str = "scenario") -> str:
        return await self.core.command_bus.dispatch(
            ConfirmPickup(correlation_id=correlation_id, transaction_id=transaction_id)
        )

    async def drain_validator_events(self, *, raise_on_error: bool = True) -> None:
        while True:
            event = await self.validator.read_event(timeout_s=0.01)
            if event is None:
                return
            try:
                await self.core.process_validator_event(event)
            except Exception:
                if raise_on_error:
                    raise
                return

    async def wait_for_runtime_processing(self, timeout_s: float = 0.25) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_s
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
            self.core.raise_runtime_failure()
        self.core.raise_runtime_failure()

    def scenario_result(
        self,
        *,
        scenario_name: str,
        success: bool,
        errors: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> ScenarioResult:
        transaction = self.core.transaction_coordinator.active()
        if transaction is None:
            unresolved = self.core.transaction_coordinator.unresolved_transactions()
            transaction = unresolved[-1] if unresolved else None
        return ScenarioResult(
            scenario_name=scenario_name,
            success=success,
            machine_state=self.core.fsm.current_state.value,
            transaction_id=transaction.transaction_id.value if transaction else None,
            transaction_status=transaction.status.value if transaction else None,
            event_types=tuple(self.recorder.event_types),
            sale_blockers=tuple(sorted(self.core.machine_status_service.runtime.status.sale_blockers)),
            errors=tuple(errors or ()),
            notes=tuple(notes or ()),
        )

    def _price_minor_units(self) -> int:
        product = self.core.inventory_service.get_product(self.product_id)
        return product.price.minor_units

    def _all_devices(self) -> list[ManagedDevice]:
        return [
            self.validator,
            self.change_dispenser,
            self.motor_controller,
            self.cooling_controller,
            self.window_controller,
            self.temperature_sensor,
            self.door_sensor,
            self.inventory_sensor,
            self.position_sensor,
            self.watchdog,
        ]
