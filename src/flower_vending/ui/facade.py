"""Application-facing facade used by the UI presenter layer."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flower_vending.app import ApplicationCore
from flower_vending.app.fsm import MachineState
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
from flower_vending.domain.entities import Product, RecoveryStatus, Slot, Transaction
from flower_vending.domain.events import DomainEvent
from flower_vending.domain.value_objects import Amount, CorrelationId, ProductId, SlotId
from flower_vending.platform.common import PlatformProfile
from flower_vending.simulators.control import (
    EventLogEntry,
    RecentEventStore,
    SimulatorControlService,
)
from flower_vending.ui.theme import ThemeName, set_theme

if TYPE_CHECKING:
    from flower_vending.runtime.bootstrap import RuntimeRepositories


logger = logging.getLogger("flower_vending.ui.facade")

EventListener = Callable[[DomainEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    product_id: str
    slot_id: str
    display_name: str
    category: str
    price_minor_units: int
    currency_code: str
    quantity: int
    available: bool
    is_bouquet: bool
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MachineUiSnapshot:
    machine_state: str
    exact_change_only: bool
    sale_blockers: tuple[str, ...]
    allow_cash_sales: bool
    allow_vending: bool
    service_mode: bool
    active_transaction_id: str | None
    payment_methods: dict[str, bool] | None = None


@dataclass(frozen=True, slots=True)
class TransactionUiSnapshot:
    transaction_id: str
    product_id: str
    slot_id: str
    product_name: str
    price_minor_units: int
    currency_code: str
    accepted_minor_units: int
    change_due_minor_units: int
    status: str
    payment_status: str
    payout_status: str
    pickup_timeout_active: bool = False
    pickup_timeout_remaining_s: float | None = None


@dataclass(frozen=True, slots=True)
class DeviceDiagnosticsRow:
    device_name: str
    state: str
    fault_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    machine: MachineUiSnapshot
    devices: tuple[DeviceDiagnosticsRow, ...]
    unresolved_transaction_ids: tuple[str, ...]
    recent_events: tuple[EventLogEntry, ...] = ()


class UiApplicationFacade:
    """Expose application-layer operations to presenters without leaking Qt into core."""

    def __init__(
        self,
        core: ApplicationCore,
        *,
        event_store: RecentEventStore | None = None,
        simulator_controls: SimulatorControlService | None = None,
        platform_profile: PlatformProfile | None = None,
        payment_methods: dict[str, bool] | None = None,
        on_service_visible_changed: Callable[[bool], None] | None = None,
        repositories: RuntimeRepositories | None = None,
        machine_id: str | None = None,
    ) -> None:
        self._core = core
        self._event_store = event_store
        self._simulator_controls = simulator_controls
        self._platform_profile = platform_profile
        self._payment_methods = payment_methods or {"cash": True}
        self._on_service_visible_changed = on_service_visible_changed
        self._service_visible = False
        self._repositories = repositories
        self._machine_id = machine_id

    def subscribe_events(self, handler: EventListener) -> None:
        self._core.event_bus.subscribe_best_effort("*", handler)

    def new_correlation_id(self) -> str:
        return CorrelationId.new().value

    def catalog_entries(self) -> tuple[CatalogEntry, ...]:
        entries: list[CatalogEntry] = []
        for product, slot in self._core.inventory_service.list_catalog():
            entries.append(self._catalog_entry(product, slot))
        return tuple(entries)

    def get_catalog_entry(self, product_id: str, slot_id: str) -> CatalogEntry:
        product, slot = self._core.inventory_service.ensure_selection(product_id, slot_id)
        return self._catalog_entry(product, slot)

    def machine_snapshot(self) -> MachineUiSnapshot:
        status = self._core.machine_status_service.runtime.status
        return MachineUiSnapshot(
            machine_state=status.machine_state,
            exact_change_only=status.exact_change_only,
            sale_blockers=tuple(sorted(status.sale_blockers)),
            allow_cash_sales=status.allow_cash_sales,
            allow_vending=status.allow_vending,
            service_mode=status.service_mode,
            active_transaction_id=status.active_transaction_id,
            payment_methods=dict(self._payment_methods) if self._payment_methods else None,
        )

    def active_transaction_snapshot(self) -> TransactionUiSnapshot | None:
        transaction = self._core.transaction_coordinator.active()
        if transaction is None:
            unresolved = self._core.transaction_coordinator.unresolved_transactions()
            transaction = unresolved[-1] if unresolved else None
        if transaction is None:
            return None
        return self._transaction_snapshot(transaction)

    def diagnostics_snapshot(self) -> DiagnosticsSnapshot:
        health = self._core.health_monitor.snapshot
        devices = (
            DeviceDiagnosticsRow("validator", health.validator_state.value, tuple()),
            DeviceDiagnosticsRow("change_dispenser", health.change_dispenser_state.value, tuple()),
            DeviceDiagnosticsRow("motor", health.motor_state.value, tuple()),
            DeviceDiagnosticsRow("cooling", health.cooling_state.value, tuple()),
            DeviceDiagnosticsRow("window", health.window_state.value, tuple()),
            DeviceDiagnosticsRow("temperature", health.temperature_sensor_state.value, tuple()),
            DeviceDiagnosticsRow("door", health.door_sensor_state.value, tuple()),
            DeviceDiagnosticsRow("inventory", health.inventory_sensor_state.value, tuple()),
            DeviceDiagnosticsRow("watchdog", health.watchdog_state.value, tuple()),
        )
        unresolved_ids = tuple(
            transaction.transaction_id.value
            for transaction in self._core.transaction_coordinator.unresolved_transactions()
        )
        return DiagnosticsSnapshot(
            machine=self.machine_snapshot(),
            devices=devices,
            unresolved_transaction_ids=unresolved_ids,
            recent_events=tuple() if self._event_store is None else self._event_store.snapshot(),
        )

    def quick_insert_denominations(self) -> tuple[int, ...]:
        if self._simulator_controls is None:
            return ()
        return self._simulator_controls.quick_insert_denominations()

    def simulator_action_ids(self) -> tuple[str, ...]:
        if self._simulator_controls is None:
            return ()
        return self._simulator_controls.available_actions()

    @property
    def platform_profile(self) -> PlatformProfile | None:
        return self._platform_profile

    async def start_cash_checkout(
        self, *, product_id: str, slot_id: str, correlation_id: str
    ) -> str:
        logger.info("start_cash_checkout", extra={"product_id": product_id, "slot_id": slot_id})
        entry = self.get_catalog_entry(product_id, slot_id)
        transaction_id = await self._core.command_bus.dispatch(
            StartPurchase(
                correlation_id=correlation_id,
                product_id=product_id,
                slot_id=slot_id,
                price_minor_units=entry.price_minor_units,
                currency=entry.currency_code,
            )
        )
        await self._core.command_bus.dispatch(
            AcceptCash(correlation_id=correlation_id, transaction_id=transaction_id)
        )
        return transaction_id

    async def cancel_purchase(self, *, transaction_id: str, correlation_id: str) -> str:
        return await self._core.command_bus.dispatch(
            CancelPurchase(correlation_id=correlation_id, transaction_id=transaction_id)
        )

    async def confirm_pickup(self, *, transaction_id: str, correlation_id: str) -> str:
        return await self._core.command_bus.dispatch(
            ConfirmPickup(correlation_id=correlation_id, transaction_id=transaction_id)
        )

    async def enter_service_mode(
        self,
        *,
        operator_id: str,
        correlation_id: str,
        pin: str,
        reason: str = "ui_service_mode_request",
    ) -> str:
        return await self._core.command_bus.dispatch(
            EnterServiceMode(
                correlation_id=correlation_id,
                operator_id=operator_id,
                pin=pin,
                reason=reason,
            )
        )

    @property
    def purchase_locked(self) -> bool:
        return self._core.service_mode_coordinator.purchase_locked

    async def exit_service_mode(
        self,
        *,
        correlation_id: str,
        operator_id: str | None = None,
    ) -> str:
        return await self._core.service_mode_coordinator.exit_service_mode(
            correlation_id=correlation_id,
            operator_id=operator_id,
        )

    async def recover_transaction(self, *, transaction_id: str, correlation_id: str) -> str:
        await self._core.command_bus.dispatch(
            RecoverInterruptedTransaction(
                correlation_id=correlation_id,
                transaction_id=transaction_id,
            )
        )
        return MachineState.RECOVERY_PENDING.value

    def set_payment_methods(self, methods: list[str]) -> None:
        self._payment_methods = {m: True for m in methods}

    def save_settings(self, settings: dict) -> None:
        if "payment_methods" in settings:
            self.set_payment_methods(settings["payment_methods"])
        if "vending_name" in settings:
            self._machine_settings = getattr(self, "_machine_settings", {})
            self._machine_settings.update(settings)

    def change_pin(self, new_pin: str) -> None:
        self._machine_settings = getattr(self, "_machine_settings", {})
        self._machine_settings["pin"] = new_pin

    def set_service_visible(self, visible: bool) -> None:
        self._service_visible = visible
        if self._on_service_visible_changed:
            self._on_service_visible_changed(visible)

    @property
    def service_visible(self) -> bool:
        return self._service_visible

    async def toggle_product(
        self,
        *,
        product_id: str,
        enabled: bool,
        operator_id: str,
        correlation_id: str,
    ) -> tuple[str, bool]:
        return await self._core.command_bus.dispatch(
            ToggleProductCommand(
                correlation_id=correlation_id,
                product_id=product_id,
                enabled=enabled,
                operator_id=operator_id,
            )
        )

    def set_product_stock(self, slot_id: str, quantity: int) -> None:
        self._core.inventory_service.set_product_stock(slot_id, quantity)

    def remove_product(self, product_id: str) -> bool:
        return self._core.inventory_service.remove_product(product_id)

    def edit_product(
        self, product_id: str, name: str, price_minor: int, category: str, stock: int
    ) -> None:
        svc = self._core.inventory_service
        try:
            product = svc._products[product_id]
        except KeyError:
            return
        current_enabled = product.enabled
        product.name = name
        product.display_name = name
        product.price = Amount(minor_units=price_minor, currency_code="RUB")
        product.category = category
        slot = next((s for s in svc._slots.values() if s.product_id.value == product_id), None)
        if slot is not None:
            slot.quantity = max(0, min(stock, slot.capacity))

    def add_product(
        self,
        product_id: str,
        name: str,
        price_minor: int,
        category: str,
        stock: int,
        enabled: bool = True,
    ) -> None:
        pid = ProductId(product_id)
        sid = SlotId(product_id)
        product = Product(
            product_id=pid,
            name=name,
            display_name=name,
            price=Amount(minor_units=price_minor, currency_code="RUB"),
            category=category,
            enabled=enabled,
        )
        slot = Slot(
            slot_id=sid,
            product_id=pid,
            capacity=max(stock, 1),
            quantity=stock,
            is_enabled=True,
        )
        self._core.inventory_service.add_product(product, slot)

    async def lock_purchase_button(
        self,
        *,
        operator_id: str,
        locked: bool = True,
        correlation_id: str,
    ) -> bool:
        return await self._core.command_bus.dispatch(
            LockPurchaseButton(
                correlation_id=correlation_id,
                operator_id=operator_id,
                locked=locked,
            )
        )

    def clear_drift(self) -> None:
        self._core.machine_status_service.clear_drift()

    def clear_simulator_recovery_state(self) -> bool:
        if (
            self._simulator_controls is None
            or self._repositories is None
            or self._machine_id is None
        ):
            return False
        unresolved = tuple(self._core.transaction_coordinator.unresolved_transactions())
        if (
            not unresolved
            and "recovery_pending"
            not in self._core.machine_status_service.runtime.status.sale_blockers
        ):
            return False

        for transaction in unresolved:
            transaction.cancel()
            transaction.recovery_status = RecoveryStatus.NONE
            self._core.transaction_coordinator.clear_active(transaction.transaction_id.value)

        self._core.machine_status_service.set_active_transaction(None)
        for blocker in tuple(self._core.machine_status_service.runtime.status.sale_blockers):
            if blocker in {"recovery_pending", "manual_review_required"}:
                self._core.machine_status_service.unblock_sales(blocker)
        if self._core.fsm.current_state in {
            MachineState.RECOVERY_PENDING,
            MachineState.MANUAL_REVIEW,
        }:
            self._core.fsm.force_state(MachineState.IDLE, "simulator_restricted_state_cleared")
            self._core.machine_status_service.set_machine_state(self._core.fsm.current_state)

        with self._repositories.database.transaction() as connection:
            for transaction in unresolved:
                self._repositories.transactions.save(transaction, _connection=connection)
            self._repositories.machine_status.save(
                self._core.machine_status_service.runtime.status,
                machine_id=self._machine_id,
                _connection=connection,
            )
        return True

    async def insert_simulated_bill(self, *, bill_minor_units: int, correlation_id: str) -> None:
        if self._simulator_controls is None:
            raise RuntimeError("simulator controls are not available")
        await self._simulator_controls.insert_bill(
            bill_minor_units=bill_minor_units,
            correlation_id=correlation_id,
        )

    async def execute_simulator_action(self, *, action_id: str, correlation_id: str) -> None:
        if self._simulator_controls is None:
            raise RuntimeError("simulator controls are not available")
        await self._simulator_controls.execute_action(
            action_id,
            correlation_id=correlation_id,
        )

    def touch(self) -> None:
        self._core.idle_timeout_coordinator.touch()

    def apply_theme(self, name: ThemeName) -> None:
        set_theme(name)

    def _catalog_entry(self, product: Product, slot: Slot) -> CatalogEntry:
        available = product.enabled and slot.is_enabled and slot.quantity > 0
        return CatalogEntry(
            product_id=product.product_id.value,
            slot_id=slot.slot_id.value,
            display_name=product.display_name,
            category=product.category,
            price_minor_units=product.price.minor_units,
            currency_code=product.price.currency.code,
            quantity=slot.quantity,
            available=available,
            is_bouquet=product.is_bouquet,
            metadata=dict(product.metadata),
        )

    def _transaction_snapshot(self, transaction: Transaction) -> TransactionUiSnapshot:
        product = self._core.inventory_service.get_product(transaction.product_id.value)
        pickup_timeout_remaining_s = self._core.pickup_timeout_coordinator.remaining_seconds(
            transaction.transaction_id.value
        )
        return TransactionUiSnapshot(
            transaction_id=transaction.transaction_id.value,
            product_id=transaction.product_id.value,
            slot_id=transaction.slot_id.value,
            product_name=product.display_name,
            price_minor_units=transaction.price.minor_units,
            currency_code=transaction.price.currency.code,
            accepted_minor_units=transaction.accepted_amount.minor_units,
            change_due_minor_units=transaction.change_due.minor_units,
            status=transaction.status.value,
            payment_status=transaction.payment_status.value,
            payout_status=transaction.payout_status.value,
            pickup_timeout_active=pickup_timeout_remaining_s is not None,
            pickup_timeout_remaining_s=pickup_timeout_remaining_s,
        )
