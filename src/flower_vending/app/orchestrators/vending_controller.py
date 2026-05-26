"""Top-level vending controller and command handlers."""

from __future__ import annotations

from flower_vending.app.event_bus import EventBus
from flower_vending.app.fsm import MachineState, StateMachineEngine
from flower_vending.app.journal import ApplicationJournal, JournalOutcome, NoopApplicationJournal
from flower_vending.app.orchestrators.payment_coordinator import PaymentCoordinator
from flower_vending.app.orchestrators.transaction_coordinator import TransactionCoordinator
from flower_vending.app.services.inventory_service import InventoryService
from flower_vending.app.services.machine_status_service import MachineStatusService
from flower_vending.devices.interfaces import InventorySensor, MotorController, WindowController
from flower_vending.domain.commands.purchase_commands import (
    AcceptCash,
    CancelPurchase,
    ConfirmPickup,
    StartPurchase,
)
from flower_vending.domain.commands.service_commands import ToggleProductCommand
from flower_vending.app.orchestrators.journaling_mixin import JournalingMixin
from flower_vending.domain.entities import Transaction
from flower_vending.domain.events import DomainEvent
from flower_vending.domain.events.machine_events import machine_event
from flower_vending.domain.events.payment_events import payment_event
from flower_vending.domain.events.vending_events import vending_event
from flower_vending.domain.exceptions import InventoryMismatchError


class VendingController(JournalingMixin):
    def __init__(
        self,
        *,
        inventory_service: InventoryService,
        payment_coordinator: PaymentCoordinator,
        transaction_coordinator: TransactionCoordinator,
        motor_controller: MotorController,
        window_controller: WindowController,
        inventory_sensor: InventorySensor | None,
        event_bus: EventBus,
        fsm: StateMachineEngine,
        machine_status_service: MachineStatusService,
        journal: ApplicationJournal | None = None,
    ) -> None:
        self._inventory_service = inventory_service
        self._payment_coordinator = payment_coordinator
        self._transaction_coordinator = transaction_coordinator
        self._motor_controller = motor_controller
        self._window_controller = window_controller
        self._inventory_sensor = inventory_sensor
        self._event_bus = event_bus
        self._fsm = fsm
        self._machine_status_service = machine_status_service
        self._journal = journal or NoopApplicationJournal()

    async def start_purchase(self, command: StartPurchase) -> str:
        self._machine_status_service.ensure_sales_allowed()
        self._inventory_service.ensure_selection(command.product_id, command.slot_id)
        if self._inventory_sensor is not None:
            presence = await self._inventory_sensor.read_slot(command.slot_id)
            if not presence.has_product or presence.confidence < 0.5:
                raise InventoryMismatchError(
                    f"inventory sensor mismatch for slot {command.slot_id}: "
                    f"has_product={presence.has_product}, confidence={presence.confidence}"
                )
        with self._journal.atomic_transaction():
            transaction = self._transaction_coordinator.create_transaction(
                correlation_id=command.correlation_id,
                product_id=command.product_id,
                slot_id=command.slot_id,
                price_minor_units=command.price_minor_units,
                currency=command.currency,
            )
            self._machine_status_service.set_active_transaction(transaction.transaction_id.value)
            self._fsm.transition(MachineState.PRODUCT_SELECTED, "product_selected")
            self._fsm.transition(MachineState.CHECKING_AVAILABILITY, "availability_check_requested")
            self._machine_status_service.ensure_sales_allowed()
            self._fsm.transition(MachineState.CHECKING_CHANGE, "change_check_requested")
            self._fsm.transition(MachineState.WAITING_FOR_PAYMENT, "waiting_for_payment")
            self._machine_status_service.set_machine_state(self._fsm.current_state)

        await self._motor_controller.stop_motion()
        await self._event_bus.publish(
            payment_event(
                "purchase_started",
                correlation_id=command.correlation_id,
                transaction_id=transaction.transaction_id.value,
                product_id=command.product_id,
                slot_id=command.slot_id,
                price_minor_units=command.price_minor_units,
            )
        )
        return transaction.transaction_id.value

    async def accept_cash(self, command: AcceptCash) -> str:
        transaction = await self._payment_coordinator.start_cash_session(
            transaction_id=command.transaction_id,
            correlation_id=command.correlation_id,
        )
        return transaction.transaction_id.value

    async def cancel_purchase(self, command: CancelPurchase) -> str:
        with self._journal.atomic_transaction():
            transaction = await self._payment_coordinator.cancel_purchase(
                transaction_id=command.transaction_id,
                correlation_id=command.correlation_id,
            )
            self._fsm.force_state(MachineState.IDLE, "transaction_cancelled")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
        return transaction.transaction_id.value

    async def confirm_pickup(self, command: ConfirmPickup) -> str:
        transaction = self._transaction_coordinator.require(command.transaction_id)
        with self._journal.atomic_transaction():
            transaction.confirm_pickup()
            self._fsm.transition(MachineState.CLOSING_DELIVERY_WINDOW, "pickup_confirmed")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._record_intent(
                transaction,
                action_name="window_close_requested",
                logical_step="confirm_pickup.close_window",
            )
        try:
            await self._window_controller.close_window(correlation_id=command.correlation_id)
        except Exception as exc:
            transaction.mark_faulted()
            self._record_outcome(
                transaction,
                action_name="window_close_requested",
                logical_step="confirm_pickup.close_window",
                outcome=JournalOutcome.AMBIGUOUS,
                error=exc.__class__.__name__,
            )
            raise
        with self._journal.atomic_transaction():
            self._record_outcome(
                transaction,
                action_name="window_close_requested",
                logical_step="confirm_pickup.close_window",
                outcome=JournalOutcome.SUCCEEDED,
            )
            transaction.mark_window_closed()
            self._fsm.transition(MachineState.COMPLETED, "delivery_window_closed")
            self._transaction_coordinator.clear_active(transaction.transaction_id.value)
            self._machine_status_service.set_active_transaction(None)
            self._fsm.transition(MachineState.IDLE, "ready_for_next_sale")
            self._machine_status_service.set_machine_state(self._fsm.current_state)

        await self._event_bus.publish(
            vending_event(
                "pickup_confirmed",
                correlation_id=command.correlation_id,
                transaction_id=transaction.transaction_id.value,
            )
        )
        await self._event_bus.publish(
            vending_event(
                "transaction_completed",
                correlation_id=command.correlation_id,
                transaction_id=transaction.transaction_id.value,
                product_id=transaction.product_id.value,
                slot_id=transaction.slot_id.value,
            )
        )
        return transaction.transaction_id.value

    async def handle_vend_authorized(self, event: DomainEvent) -> None:
        if event.transaction_id is None:
            return
        transaction = self._transaction_coordinator.require(event.transaction_id)
        with self._journal.atomic_transaction():
            transaction.authorize_vend()
            self._fsm.transition(MachineState.DISPENSING_PRODUCT, "vend_authorized")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._record_intent(
                transaction,
                action_name="motor_vend_requested",
                logical_step="handle_vend_authorized.vend_motor",
                slot_id=transaction.slot_id.value,
            )
        await self._event_bus.publish(
            vending_event(
                "product_dispense_requested",
                correlation_id=transaction.correlation_id.value,
                transaction_id=transaction.transaction_id.value,
                slot_id=transaction.slot_id.value,
            )
        )
        try:
            await self._motor_controller.stop_motion()
            await self._motor_controller.vend_slot(
                slot_id=transaction.slot_id.value,
                correlation_id=transaction.correlation_id.value,
            )
        except Exception:
            transaction.mark_faulted()
            self._record_outcome(
                transaction,
                action_name="motor_vend_requested",
                logical_step="handle_vend_authorized.vend_motor",
                outcome=JournalOutcome.AMBIGUOUS,
                slot_id=transaction.slot_id.value,
            )
            self._transaction_coordinator.clear_active(transaction.transaction_id.value)
            self._machine_status_service.set_active_transaction(None)
            self._fsm.transition(MachineState.FAULT, "motor_fault")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            await self._event_bus.publish(
                vending_event("machine_faulted", correlation_id=transaction.correlation_id.value,
                              transaction_id=transaction.transaction_id.value, faults=["motor_fault"])
            )
            raise
        with self._journal.atomic_transaction():
            self._record_outcome(
                transaction,
                action_name="motor_vend_requested",
                logical_step="handle_vend_authorized.vend_motor",
                outcome=JournalOutcome.SUCCEEDED,
                slot_id=transaction.slot_id.value,
            )
            self._record_intent(
                transaction,
                action_name="inventory_decrement",
                logical_step="handle_vend_authorized.mark_vended",
                slot_id=transaction.slot_id.value,
            )
            self._inventory_service.mark_vended(transaction.slot_id.value)
            self._record_outcome(
                transaction,
                action_name="inventory_decrement",
                logical_step="handle_vend_authorized.mark_vended",
                outcome=JournalOutcome.SUCCEEDED,
                slot_id=transaction.slot_id.value,
            )
            transaction.mark_product_dispensed()
            self._fsm.transition(MachineState.OPENING_DELIVERY_WINDOW, "product_dispensed")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            self._record_intent(
                transaction,
                action_name="window_open_requested",
                logical_step="handle_vend_authorized.open_window",
            )

        await self._event_bus.publish(
            vending_event(
                "product_dispensed",
                correlation_id=transaction.correlation_id.value,
                transaction_id=transaction.transaction_id.value,
                slot_id=transaction.slot_id.value,
            )
        )
        try:
            await self._window_controller.open_window(correlation_id=transaction.correlation_id.value)
        except Exception:
            transaction.mark_faulted()
            self._record_outcome(
                transaction,
                action_name="window_open_requested",
                logical_step="handle_vend_authorized.open_window",
                outcome=JournalOutcome.AMBIGUOUS,
            )
            self._transaction_coordinator.clear_active(transaction.transaction_id.value)
            self._machine_status_service.set_active_transaction(None)
            self._fsm.transition(MachineState.FAULT, "delivery_window_fault")
            self._machine_status_service.set_machine_state(self._fsm.current_state)
            await self._event_bus.publish(
                vending_event("machine_faulted", correlation_id=transaction.correlation_id.value,
                              transaction_id=transaction.transaction_id.value, faults=["delivery_window_fault"])
            )
            raise
        with self._journal.atomic_transaction():
            self._record_outcome(
                transaction,
                action_name="window_open_requested",
                logical_step="handle_vend_authorized.open_window",
                outcome=JournalOutcome.SUCCEEDED,
            )
            transaction.mark_window_opened()
            self._fsm.transition(MachineState.WAITING_FOR_CUSTOMER_PICKUP, "delivery_window_opened")
            self._machine_status_service.set_machine_state(self._fsm.current_state)

        await self._event_bus.publish(
            vending_event(
                "delivery_window_opened",
                correlation_id=transaction.correlation_id.value,
                transaction_id=transaction.transaction_id.value,
            )
        )

    async def handle_toggle_product(self, command: ToggleProductCommand) -> tuple[str, bool]:
        product, slot = self._inventory_service.set_product_enabled(
            command.product_id, command.enabled,
        )
        state = product.enabled
        self._machine_status_service.set_machine_state(self._fsm.current_state)
        await self._event_bus.publish(
            machine_event(
                "product_toggled",
                correlation_id=command.correlation_id,
                product_id=command.product_id,
                enabled=str(state),
                operator_id=command.operator_id,
            )
        )
        return command.product_id, state

